import sqlite3
from datetime import datetime, date
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from app.auth import login_required
from app.db import get_db
from app.validators import (
    time_to_minutes,
    minutes_to_time,
    check_appointment_overlap,
    ALLOWED_APPOINTMENT_STATUSES,
)

bp = Blueprint("appointments", __name__, url_prefix="/appointments")


@bp.route("/")
@login_required
def index():
    """List appointments with search and multi-criteria filters (Patient, Doctor, Date, Status)."""
    db = get_db()
    search = request.args.get("search", "").strip()
    filter_patient = request.args.get("patient_id", "").strip()
    filter_doctor = request.args.get("doctor_id", "").strip()
    filter_date = request.args.get("date", "").strip()
    filter_status = request.args.get("status", "all").strip()

    query = """
        SELECT 
            a.Appointment_ID,
            a.Patient_id,
            a.Doctor_ID,
            a.A_Date,
            a.A_Time,
            a.Reason,
            a.Duration_Min,
            a.Status,
            a.Created_At,
            p.P_Name AS Patient_Name,
            p.Blood_Group,
            d.D_Name AS Doctor_Name,
            d.D_Qualification
        FROM Appointment a
        JOIN Patient p ON a.Patient_id = p.Patient_id
        JOIN Doctor d ON a.Doctor_ID = d.Doctor_ID
        WHERE 1=1
    """
    params = []

    # Search filter (Reason, Patient Name, or Doctor Name)
    if search:
        query += " AND (a.Reason LIKE ? OR p.P_Name LIKE ? OR d.D_Name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    # Patient filter
    if filter_patient and filter_patient.isdigit():
        query += " AND a.Patient_id = ?"
        params.append(int(filter_patient))

    # Doctor filter
    if filter_doctor and filter_doctor.isdigit():
        query += " AND a.Doctor_ID = ?"
        params.append(int(filter_doctor))

    # Date filter
    if filter_date:
        query += " AND a.A_Date = ?"
        params.append(filter_date)

    # Status filter
    if filter_status and filter_status != "all":
        query += " AND a.Status = ?"
        params.append(filter_status)

    query += " ORDER BY a.A_Date DESC, a.A_Time DESC"
    appointments = db.execute(query, params).fetchall()

    # Auxiliary data for filter dropdowns
    patients = db.execute("SELECT Patient_id, P_Name FROM Patient ORDER BY P_Name").fetchall()
    doctors = db.execute("SELECT Doctor_ID, D_Name FROM Doctor ORDER BY D_Name").fetchall()

    # Status counts
    total_count = db.execute("SELECT COUNT(*) FROM Appointment").fetchone()[0]
    scheduled_count = db.execute("SELECT COUNT(*) FROM Appointment WHERE Status = 'Scheduled'").fetchone()[0]
    completed_count = db.execute("SELECT COUNT(*) FROM Appointment WHERE Status = 'Completed'").fetchone()[0]
    cancelled_count = db.execute("SELECT COUNT(*) FROM Appointment WHERE Status = 'Cancelled'").fetchone()[0]

    return render_template(
        "appointments/index.html",
        appointments=appointments,
        search=search,
        filter_patient=filter_patient,
        filter_doctor=filter_doctor,
        filter_date=filter_date,
        filter_status=filter_status,
        patients=patients,
        doctors=doctors,
        total_count=total_count,
        scheduled_count=scheduled_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
        allowed_statuses=ALLOWED_APPOINTMENT_STATUSES,
    )


@bp.route("/create", methods=("GET", "POST"))
@login_required
def create():
    """Schedule a new appointment with conflict detection and clinic hour enforcement."""
    db = get_db()
    clinic_open = current_app.config.get("CLINIC_OPEN_TIME", "09:00")
    clinic_close = current_app.config.get("CLINIC_CLOSE_TIME", "17:00")
    default_duration = current_app.config.get("DEFAULT_APPOINTMENT_DURATION", 30)

    if request.method == "POST":
        patient_id_raw = request.form.get("patient_id", "").strip()
        doctor_id_raw = request.form.get("doctor_id", "").strip()
        date_str = request.form.get("date", "").strip()
        time_str = request.form.get("time", "").strip()
        reason = request.form.get("reason", "").strip()
        duration_raw = request.form.get("duration", str(default_duration)).strip()

        errors = []

        # 1. Patient verification
        patient = None
        if not patient_id_raw or not patient_id_raw.isdigit():
            errors.append("Please select a valid patient.")
        else:
            patient = db.execute(
                "SELECT Patient_id, P_Name, is_active FROM Patient WHERE Patient_id = ?",
                (int(patient_id_raw),),
            ).fetchone()
            if not patient:
                errors.append("The selected patient does not exist.")

        # 2. Doctor verification (must be active)
        doctor = None
        if not doctor_id_raw or not doctor_id_raw.isdigit():
            errors.append("Please select a valid doctor.")
        else:
            doctor = db.execute(
                "SELECT Doctor_ID, D_Name, is_active FROM Doctor WHERE Doctor_ID = ?",
                (int(doctor_id_raw),),
            ).fetchone()
            if not doctor:
                errors.append("The selected doctor does not exist.")
            elif doctor["is_active"] != 1:
                errors.append(f"Dr. {doctor['D_Name']} is currently inactive/off-duty and cannot accept new appointments.")

        # 3. Reason validation
        if not reason:
            errors.append("Please enter the clinical reason for the appointment.")
        elif len(reason) > 250:
            errors.append("Reason must be 250 characters or less.")

        # 4. Duration validation
        duration = default_duration
        if duration_raw:
            try:
                duration = int(duration_raw)
                if duration <= 0 or duration > 180:
                    errors.append("Duration must be between 5 and 180 minutes.")
            except ValueError:
                errors.append("Duration must be a valid number.")

        # 5. Date validation (must not be in the past)
        if not date_str:
            errors.append("Please select an appointment date.")
        else:
            try:
                appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if appt_date < date.today():
                    errors.append("Appointment date cannot be in the past.")
            except ValueError:
                errors.append("Date must be in YYYY-MM-DD format.")

        # 6. Time and Clinic Hours validation
        start_min = time_to_minutes(time_str)
        if start_min is None:
            errors.append("Please enter a valid appointment time in HH:MM format.")
        else:
            open_min = time_to_minutes(clinic_open)
            close_min = time_to_minutes(clinic_close)
            end_min = start_min + duration

            if start_min < open_min:
                errors.append(f"Appointment time ({time_str}) cannot be earlier than clinic opening hours ({clinic_open}).")
            elif end_min > close_min:
                errors.append(
                    f"Appointment ({time_str} to {minutes_to_time(end_min)}) extends beyond clinic closing hours ({clinic_close})."
                )

        # 7. Doctor Overlap Conflict Check
        if not errors and doctor and start_min is not None:
            has_conflict, conflict = check_appointment_overlap(
                db, int(doctor_id_raw), date_str, start_min, start_min + duration
            )
            if has_conflict:
                doc_title = doctor["D_Name"] if doctor["D_Name"].startswith("Dr.") else f"Dr. {doctor['D_Name']}"
                errors.append(
                    f"Scheduling Conflict: {doc_title} already has an appointment scheduled "
                    f"from {conflict['Start_Time']} to {conflict['End_Time']} on {date_str}. "
                    f"Please choose another time slot or another doctor."
                )

        # 8. Database Transaction Execution
        if not errors:
            try:
                cur = db.execute(
                    """INSERT INTO Appointment 
                       (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
                       VALUES (?, ?, ?, ?, ?, ?, 'Scheduled')""",
                    (int(patient_id_raw), int(doctor_id_raw), date_str, time_str, reason, duration),
                )
                db.commit()
                new_appt_id = cur.lastrowid
                doc_title = doctor["D_Name"] if doctor["D_Name"].startswith("Dr.") else f"Dr. {doctor['D_Name']}"
                flash(
                    f"Appointment #{new_appt_id} scheduled successfully for {patient['P_Name']} "
                    f"with {doc_title} on {date_str} at {time_str}.",
                    "success",
                )
                return redirect(url_for("appointments.detail", appointment_id=new_appt_id))
            except sqlite3.Error as e:
                flash(f"Database error creating appointment: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    # Fetch active patients and active doctors for dropdowns
    active_patients = db.execute("SELECT Patient_id, P_Name, Blood_Group FROM Patient WHERE is_active = 1 ORDER BY P_Name").fetchall()
    active_doctors = db.execute("SELECT Doctor_ID, D_Name, D_Qualification FROM Doctor WHERE is_active = 1 ORDER BY D_Name").fetchall()

    # Pre-select IDs if passed in query params
    pre_patient = request.args.get("patient_id", "")
    pre_doctor = request.args.get("doctor_id", "")

    return render_template(
        "appointments/create.html",
        active_patients=active_patients,
        active_doctors=active_doctors,
        pre_patient=pre_patient,
        pre_doctor=pre_doctor,
        clinic_open=clinic_open,
        clinic_close=clinic_close,
        default_duration=default_duration,
    )


@bp.route("/<int:appointment_id>")
@login_required
def detail(appointment_id):
    """View appointment record details, participants, and status management actions."""
    db = get_db()
    appointment = db.execute(
        """
        SELECT 
            a.*,
            p.P_Name AS Patient_Name,
            p.P_Age,
            p.P_Gender,
            p.Blood_Group,
            d.D_Name AS Doctor_Name,
            d.D_Qualification,
            d.D_Phone AS Doctor_Phone
        FROM Appointment a
        JOIN Patient p ON a.Patient_id = p.Patient_id
        JOIN Doctor d ON a.Doctor_ID = d.Doctor_ID
        WHERE a.Appointment_ID = ?
        """,
        (appointment_id,),
    ).fetchone()

    if appointment is None:
        flash(f"Appointment #{appointment_id} not found.", "warning")
        return redirect(url_for("appointments.index"))

    start_min = time_to_minutes(appointment["A_Time"])
    end_time = minutes_to_time(start_min + appointment["Duration_Min"]) if start_min else "N/A"

    return render_template(
        "appointments/detail.html",
        appointment=appointment,
        end_time=end_time,
    )


@bp.route("/<int:appointment_id>/edit", methods=("GET", "POST"))
@login_required
def edit(appointment_id):
    """Reschedule or edit appointment details with self-exclusion from conflict check."""
    db = get_db()
    appointment = db.execute("SELECT * FROM Appointment WHERE Appointment_ID = ?", (appointment_id,)).fetchone()
    if appointment is None:
        flash(f"Appointment #{appointment_id} not found.", "warning")
        return redirect(url_for("appointments.index"))

    clinic_open = current_app.config.get("CLINIC_OPEN_TIME", "09:00")
    clinic_close = current_app.config.get("CLINIC_CLOSE_TIME", "17:00")
    default_duration = current_app.config.get("DEFAULT_APPOINTMENT_DURATION", 30)

    if request.method == "POST":
        doctor_id_raw = request.form.get("doctor_id", "").strip()
        date_str = request.form.get("date", "").strip()
        time_str = request.form.get("time", "").strip()
        reason = request.form.get("reason", "").strip()
        duration_raw = request.form.get("duration", str(appointment["Duration_Min"])).strip()
        status = request.form.get("status", appointment["Status"]).strip()

        errors = []

        # Doctor verification
        doctor = None
        if not doctor_id_raw or not doctor_id_raw.isdigit():
            errors.append("Please select a valid doctor.")
        else:
            doctor = db.execute("SELECT Doctor_ID, D_Name, is_active FROM Doctor WHERE Doctor_ID = ?", (int(doctor_id_raw),)).fetchone()
            if not doctor:
                errors.append("The selected doctor does not exist.")

        # Reason
        if not reason:
            errors.append("Please enter the clinical reason.")
        elif len(reason) > 250:
            errors.append("Reason must be 250 characters or less.")

        # Duration
        duration = default_duration
        if duration_raw:
            try:
                duration = int(duration_raw)
                if duration <= 0 or duration > 180:
                    errors.append("Duration must be between 5 and 180 minutes.")
            except ValueError:
                errors.append("Duration must be a valid number.")

        # Date
        if not date_str:
            errors.append("Please select a date.")
        else:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                errors.append("Date must be in YYYY-MM-DD format.")

        # Time and Clinic Hours
        start_min = time_to_minutes(time_str)
        if start_min is None:
            errors.append("Please enter a valid time in HH:MM format.")
        else:
            open_min = time_to_minutes(clinic_open)
            close_min = time_to_minutes(clinic_close)
            end_min = start_min + duration

            if start_min < open_min or end_min > close_min:
                errors.append(f"Appointment must fall within clinic hours ({clinic_open} to {clinic_close}).")

        # Conflict check - excluding this appointment itself
        if not errors and doctor and start_min is not None and status != "Cancelled":
            has_conflict, conflict = check_appointment_overlap(
                db, int(doctor_id_raw), date_str, start_min, start_min + duration, exclude_appointment_id=appointment_id
            )
            if has_conflict:
                doc_title = doctor["D_Name"] if doctor["D_Name"].startswith("Dr.") else f"Dr. {doctor['D_Name']}"
                errors.append(
                    f"Scheduling Conflict: {doc_title} already has an appointment scheduled "
                    f"from {conflict['Start_Time']} to {conflict['End_Time']} on {date_str}."
                )

        if not errors:
            try:
                db.execute(
                    """UPDATE Appointment
                       SET Doctor_ID = ?, A_Date = ?, A_Time = ?, Reason = ?, Duration_Min = ?, Status = ?
                       WHERE Appointment_ID = ?""",
                    (int(doctor_id_raw), date_str, time_str, reason, duration, status, appointment_id),
                )
                db.commit()
                flash(f"Appointment #{appointment_id} updated successfully.", "success")
                return redirect(url_for("appointments.detail", appointment_id=appointment_id))
            except sqlite3.Error as e:
                flash(f"Database error updating appointment: {e}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    # Fetch active doctors for reassignment, including the currently assigned doctor even if inactive
    doctors = db.execute(
        "SELECT Doctor_ID, D_Name, D_Qualification FROM Doctor WHERE is_active = 1 OR Doctor_ID = ? ORDER BY D_Name",
        (appointment["Doctor_ID"],),
    ).fetchall()
    patient = db.execute("SELECT Patient_id, P_Name FROM Patient WHERE Patient_id = ?", (appointment["Patient_id"],)).fetchone()

    return render_template(
        "appointments/edit.html",
        appointment=appointment,
        patient=patient,
        doctors=doctors,
        clinic_open=clinic_open,
        clinic_close=clinic_close,
        allowed_statuses=ALLOWED_APPOINTMENT_STATUSES,
    )


@bp.route("/<int:appointment_id>/cancel", methods=("POST",))
@login_required
def cancel(appointment_id):
    """Cancel appointment. Cancelled appointments release the slot for other bookings."""
    db = get_db()
    appt = db.execute("SELECT Appointment_ID, Status FROM Appointment WHERE Appointment_ID = ?", (appointment_id,)).fetchone()
    if not appt:
        flash(f"Appointment #{appointment_id} not found.", "warning")
        return redirect(url_for("appointments.index"))

    db.execute("UPDATE Appointment SET Status = 'Cancelled' WHERE Appointment_ID = ?", (appointment_id,))
    db.commit()
    flash(f"Appointment #{appointment_id} has been cancelled. The time slot is now available for other bookings.", "info")
    return redirect(request.referrer or url_for("appointments.detail", appointment_id=appointment_id))


@bp.route("/<int:appointment_id>/complete", methods=("POST",))
@login_required
def complete(appointment_id):
    """Mark appointment as completed."""
    db = get_db()
    appt = db.execute("SELECT Appointment_ID FROM Appointment WHERE Appointment_ID = ?", (appointment_id,)).fetchone()
    if not appt:
        flash(f"Appointment #{appointment_id} not found.", "warning")
        return redirect(url_for("appointments.index"))

    db.execute("UPDATE Appointment SET Status = 'Completed' WHERE Appointment_ID = ?", (appointment_id,))
    db.commit()
    flash(f"Appointment #{appointment_id} marked as completed.", "success")
    return redirect(request.referrer or url_for("appointments.detail", appointment_id=appointment_id))
