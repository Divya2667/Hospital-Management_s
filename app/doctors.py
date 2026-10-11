import sqlite3
from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from app.auth import login_required
from app.db import get_db
from app.validators import validate_doctor

bp = Blueprint("doctors", __name__, url_prefix="/doctors")


@bp.route("/")
@login_required
def index():
    """List all doctors with search (by Name, Qualification, or ID) and status filtering."""
    db = get_db()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()

    query = "SELECT * FROM Doctor WHERE 1=1"
    params = []

    # Search filter
    if search:
        if search.isdigit():
            query += " AND (Doctor_ID = ? OR D_Name LIKE ? OR D_Qualification LIKE ?)"
            params.extend([int(search), f"%{search}%", f"%{search}%"])
        else:
            query += " AND (D_Name LIKE ? OR D_Qualification LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

    # Status filter
    if status_filter == "active":
        query += " AND is_active = 1"
    elif status_filter == "inactive":
        query += " AND is_active = 0"

    query += " ORDER BY Doctor_ID DESC"
    doctors = db.execute(query, params).fetchall()

    # Total counts for filter pills
    active_count = db.execute("SELECT COUNT(*) FROM Doctor WHERE is_active = 1").fetchone()[0]
    total_count = db.execute("SELECT COUNT(*) FROM Doctor").fetchone()[0]
    inactive_count = total_count - active_count

    return render_template(
        "doctors/index.html",
        doctors=doctors,
        search=search,
        status_filter=status_filter,
        active_count=active_count,
        inactive_count=inactive_count,
        total_count=total_count,
    )


@bp.route("/create", methods=("GET", "POST"))
@login_required
def create():
    """Register a new doctor."""
    if request.method == "POST":
        name = request.form.get("name")
        qualification = request.form.get("qualification")
        experience_str = request.form.get("experience")
        phone = request.form.get("phone")

        errors, cleaned_data = validate_doctor(name, qualification, experience_str, phone)

        db = get_db()
        # Graceful check for duplicate phone number
        if not errors:
            existing = db.execute(
                "SELECT Doctor_ID, D_Name FROM Doctor WHERE D_Phone = ?",
                (cleaned_data["D_Phone"],),
            ).fetchone()
            if existing:
                errors.append(f"Phone number is already associated with Dr. {existing['D_Name']} (ID: #{existing['Doctor_ID']}).")

        if not errors:
            try:
                cur = db.execute(
                    """INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active)
                       VALUES (?, ?, ?, ?, 1)""",
                    (
                        cleaned_data["D_Name"],
                        cleaned_data["D_Qualification"],
                        cleaned_data["Experience"],
                        cleaned_data["D_Phone"],
                    ),
                )
                db.commit()
                new_doctor_id = cur.lastrowid
                flash(f"Doctor '{cleaned_data['D_Name']}' (ID: #{new_doctor_id}) registered successfully.", "success")
                return redirect(url_for("doctors.detail", doctor_id=new_doctor_id))
            except sqlite3.Error as e:
                flash(f"Database error registering doctor: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    return render_template("doctors/create.html")


@bp.route("/<int:doctor_id>")
@login_required
def detail(doctor_id):
    """View doctor profile details and their assigned clinical appointments."""
    db = get_db()
    doctor = db.execute("SELECT * FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()
    if doctor is None:
        flash(f"Doctor #{doctor_id} was not found.", "warning")
        return redirect(url_for("doctors.index"))

    # Appointments assigned to this doctor with Patient details
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
            p.Patient_id,
            p.P_Name AS Patient_Name,
            p.Blood_Group
        FROM Appointment a
        JOIN Patient p ON a.Patient_id = p.Patient_id
        WHERE a.Doctor_ID = ?
        ORDER BY a.A_Date DESC, a.A_Time DESC
        """,
        (doctor_id,),
    ).fetchall()

    scheduled_count = sum(1 for a in appointments if a["Status"] == "Scheduled")
    completed_count = sum(1 for a in appointments if a["Status"] == "Completed")

    return render_template(
        "doctors/detail.html",
        doctor=doctor,
        appointments=appointments,
        scheduled_count=scheduled_count,
        completed_count=completed_count,
    )


@bp.route("/<int:doctor_id>/edit", methods=("GET", "POST"))
@login_required
def edit(doctor_id):
    """Edit doctor information."""
    db = get_db()
    doctor = db.execute("SELECT * FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()
    if doctor is None:
        flash(f"Doctor #{doctor_id} was not found.", "warning")
        return redirect(url_for("doctors.index"))

    if request.method == "POST":
        name = request.form.get("name")
        qualification = request.form.get("qualification")
        experience_str = request.form.get("experience")
        phone = request.form.get("phone")

        errors, cleaned_data = validate_doctor(name, qualification, experience_str, phone)

        # Check duplicate phone for other doctors
        if not errors:
            duplicate = db.execute(
                "SELECT Doctor_ID, D_Name FROM Doctor WHERE D_Phone = ? AND Doctor_ID != ?",
                (cleaned_data["D_Phone"], doctor_id),
            ).fetchone()
            if duplicate:
                errors.append(f"Phone number is already associated with Dr. {duplicate['D_Name']} (ID: #{duplicate['Doctor_ID']}).")

        if not errors:
            try:
                db.execute(
                    """UPDATE Doctor
                       SET D_Name = ?, D_Qualification = ?, Experience = ?, D_Phone = ?
                       WHERE Doctor_ID = ?""",
                    (
                        cleaned_data["D_Name"],
                        cleaned_data["D_Qualification"],
                        cleaned_data["Experience"],
                        cleaned_data["D_Phone"],
                        doctor_id,
                    ),
                )
                db.commit()
                flash(f"Doctor #{doctor_id} updated successfully.", "success")
                return redirect(url_for("doctors.detail", doctor_id=doctor_id))
            except sqlite3.Error as e:
                flash(f"Database error updating doctor: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    return render_template("doctors/edit.html", doctor=doctor)


@bp.route("/<int:doctor_id>/toggle-status", methods=("POST",))
@login_required
def toggle_status(doctor_id):
    """Toggle doctor active / inactive on-duty status."""
    db = get_db()
    doctor = db.execute("SELECT Doctor_ID, D_Name, is_active FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()
    if doctor is None:
        flash(f"Doctor #{doctor_id} not found.", "warning")
        return redirect(url_for("doctors.index"))

    new_status = 0 if doctor["is_active"] == 1 else 1
    db.execute("UPDATE Doctor SET is_active = ? WHERE Doctor_ID = ?", (new_status, doctor_id))
    db.commit()

    action = "deactivated (off-duty)" if new_status == 0 else "reactivated (on-duty)"
    flash(f"Doctor '{doctor['D_Name']}' has been {action}.", "info")
    return redirect(request.referrer or url_for("doctors.detail", doctor_id=doctor_id))


@bp.route("/<int:doctor_id>/delete", methods=("POST",))
@login_required
def delete(doctor_id):
    """Safely handle doctor deletion. Blocks deletion if doctor has existing appointments."""
    db = get_db()
    doctor = db.execute("SELECT Doctor_ID, D_Name FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()
    if doctor is None:
        flash(f"Doctor #{doctor_id} not found.", "warning")
        return redirect(url_for("doctors.index"))

    # Check for historical appointment records
    appt_count = db.execute("SELECT COUNT(*) FROM Appointment WHERE Doctor_ID = ?", (doctor_id,)).fetchone()[0]
    if appt_count > 0:
        flash(
            f"Cannot delete Doctor '{doctor['D_Name']}' (ID: #{doctor_id}): "
            f"This doctor has {appt_count} clinical appointment record(s). "
            f"Please deactivate the doctor instead to preserve historical appointment records.",
            "danger",
        )
        return redirect(url_for("doctors.detail", doctor_id=doctor_id))

    try:
        db.execute("DELETE FROM Doctor WHERE Doctor_ID = ?", (doctor_id,))
        db.commit()
        flash(f"Doctor record '{doctor['D_Name']}' (ID: #{doctor_id}) was successfully deleted.", "success")
        return redirect(url_for("doctors.index"))
    except sqlite3.IntegrityError:
        flash(
            f"Cannot delete doctor #{doctor_id} due to active database foreign key constraints.",
            "danger",
        )
        return redirect(url_for("doctors.detail", doctor_id=doctor_id))
