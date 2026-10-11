import sqlite3
from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
    abort,
)
from app.auth import login_required
from app.db import get_db
from app.validators import (
    validate_patient,
    ALLOWED_GENDERS,
    ALLOWED_BLOOD_GROUPS,
)

bp = Blueprint("patients", __name__, url_prefix="/patients")


@bp.route("/")
@login_required
def index():
    """List patients with search and status filtering."""
    db = get_db()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()

    query = "SELECT * FROM Patient WHERE 1=1"
    params = []

    # Search filter (by Name or Patient ID)
    if search:
        if search.isdigit():
            query += " AND (Patient_id = ? OR P_Name LIKE ?)"
            params.extend([int(search), f"%{search}%"])
        else:
            query += " AND P_Name LIKE ?"
            params.append(f"%{search}%")

    # Status filter
    if status_filter == "active":
        query += " AND is_active = 1"
    elif status_filter == "inactive":
        query += " AND is_active = 0"

    query += " ORDER BY Patient_id DESC"
    patients = db.execute(query, params).fetchall()

    # Total counts for filter pills
    active_count = db.execute("SELECT COUNT(*) FROM Patient WHERE is_active = 1").fetchone()[0]
    total_count = db.execute("SELECT COUNT(*) FROM Patient").fetchone()[0]
    inactive_count = total_count - active_count

    return render_template(
        "patients/index.html",
        patients=patients,
        search=search,
        status_filter=status_filter,
        active_count=active_count,
        inactive_count=inactive_count,
        total_count=total_count,
    )


@bp.route("/create", methods=("GET", "POST"))
@login_required
def create():
    """Register a new patient."""
    if request.method == "POST":
        name = request.form.get("name")
        age_str = request.form.get("age")
        gender = request.form.get("gender")
        blood_group = request.form.get("blood_group")

        errors, cleaned_data = validate_patient(name, age_str, gender, blood_group)

        if not errors:
            db = get_db()
            try:
                cur = db.execute(
                    """INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active)
                       VALUES (?, ?, ?, ?, 1)""",
                    (
                        cleaned_data["P_Name"],
                        cleaned_data["P_Age"],
                        cleaned_data["P_Gender"],
                        cleaned_data["Blood_Group"],
                    ),
                )
                db.commit()
                new_patient_id = cur.lastrowid
                flash(f"Patient '{cleaned_data['P_Name']}' (ID: #{new_patient_id}) registered successfully.", "success")
                return redirect(url_for("patients.detail", patient_id=new_patient_id))
            except sqlite3.Error as e:
                flash(f"Database error registering patient: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    return render_template(
        "patients/create.html",
        allowed_genders=ALLOWED_GENDERS,
        allowed_blood_groups=ALLOWED_BLOOD_GROUPS,
    )


@bp.route("/<int:patient_id>")
@login_required
def detail(patient_id):
    """View patient details, complete appointment history, and billing history."""
    db = get_db()
    patient = db.execute("SELECT * FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()
    if patient is None:
        flash(f"Patient #{patient_id} was not found.", "warning")
        return redirect(url_for("patients.index"))

    # Patient's appointment history with assigned Doctor details
    appointments = db.execute(
        """
        SELECT 
            a.Appointment_ID,
            a.A_Date,
            a.A_Time,
            a.Reason,
            a.Duration_Min,
            a.Status,
            a.Created_At,
            d.Doctor_ID,
            d.D_Name AS Doctor_Name,
            d.D_Qualification
        FROM Appointment a
        JOIN Doctor d ON a.Doctor_ID = d.Doctor_ID
        WHERE a.Patient_id = ?
        ORDER BY a.A_Date DESC, a.A_Time DESC
        """,
        (patient_id,),
    ).fetchall()

    # Patient's billing history
    bills = db.execute(
        """
        SELECT Bill_ID, B_Date, B_Amount, Pay_Mode, Created_At
        FROM Bill
        WHERE Patient_id = ?
        ORDER BY Bill_ID DESC
        """,
        (patient_id,),
    ).fetchall()

    # Calculate total bills amount for this patient
    total_billed = sum(bill["B_Amount"] for bill in bills)

    return render_template(
        "patients/detail.html",
        patient=patient,
        appointments=appointments,
        bills=bills,
        total_billed=total_billed,
    )


@bp.route("/<int:patient_id>/edit", methods=("GET", "POST"))
@login_required
def edit(patient_id):
    """Edit patient information."""
    db = get_db()
    patient = db.execute("SELECT * FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()
    if patient is None:
        flash(f"Patient #{patient_id} was not found.", "warning")
        return redirect(url_for("patients.index"))

    if request.method == "POST":
        name = request.form.get("name")
        age_str = request.form.get("age")
        gender = request.form.get("gender")
        blood_group = request.form.get("blood_group")

        errors, cleaned_data = validate_patient(name, age_str, gender, blood_group)

        if not errors:
            try:
                db.execute(
                    """UPDATE Patient
                       SET P_Name = ?, P_Age = ?, P_Gender = ?, Blood_Group = ?
                       WHERE Patient_id = ?""",
                    (
                        cleaned_data["P_Name"],
                        cleaned_data["P_Age"],
                        cleaned_data["P_Gender"],
                        cleaned_data["Blood_Group"],
                        patient_id,
                    ),
                )
                db.commit()
                flash(f"Patient #{patient_id} updated successfully.", "success")
                return redirect(url_for("patients.detail", patient_id=patient_id))
            except sqlite3.Error as e:
                flash(f"Database error updating patient: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    return render_template(
        "patients/edit.html",
        patient=patient,
        allowed_genders=ALLOWED_GENDERS,
        allowed_blood_groups=ALLOWED_BLOOD_GROUPS,
    )


@bp.route("/<int:patient_id>/toggle-status", methods=("POST",))
@login_required
def toggle_status(patient_id):
    """Toggle patient active / inactive status safely without destroying history."""
    db = get_db()
    patient = db.execute("SELECT Patient_id, P_Name, is_active FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()
    if patient is None:
        flash(f"Patient #{patient_id} not found.", "warning")
        return redirect(url_for("patients.index"))

    new_status = 0 if patient["is_active"] == 1 else 1
    db.execute("UPDATE Patient SET is_active = ? WHERE Patient_id = ?", (new_status, patient_id))
    db.commit()

    action = "deactivated" if new_status == 0 else "reactivated"
    flash(f"Patient '{patient['P_Name']}' has been {action}.", "info")
    return redirect(request.referrer or url_for("patients.detail", patient_id=patient_id))


@bp.route("/<int:patient_id>/delete", methods=("POST",))
@login_required
def delete(patient_id):
    """Safely handle deletion attempts. Blocks deletion if patient has appointments or bills."""
    db = get_db()
    patient = db.execute("SELECT Patient_id, P_Name FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()
    if patient is None:
        flash(f"Patient #{patient_id} not found.", "warning")
        return redirect(url_for("patients.index"))

    # Check for historical records to protect relational integrity
    appt_count = db.execute("SELECT COUNT(*) FROM Appointment WHERE Patient_id = ?", (patient_id,)).fetchone()[0]
    bill_count = db.execute("SELECT COUNT(*) FROM Bill WHERE Patient_id = ?", (patient_id,)).fetchone()[0]

    if appt_count > 0 or bill_count > 0:
        flash(
            f"Cannot delete Patient '{patient['P_Name']}' (ID: #{patient_id}): "
            f"This patient has {appt_count} appointment(s) and {bill_count} billing record(s). "
            f"Please deactivate the patient instead to preserve historical records.",
            "danger",
        )
        return redirect(url_for("patients.detail", patient_id=patient_id))

    try:
        db.execute("DELETE FROM Patient WHERE Patient_id = ?", (patient_id,))
        db.commit()
        flash(f"Patient record '{patient['P_Name']}' (ID: #{patient_id}) was successfully deleted.", "success")
        return redirect(url_for("patients.index"))
    except sqlite3.IntegrityError:
        flash(
            f"Cannot delete patient #{patient_id} due to active database foreign key constraints.",
            "danger",
        )
        return redirect(url_for("patients.detail", patient_id=patient_id))
