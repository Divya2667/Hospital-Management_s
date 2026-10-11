from flask import Blueprint, render_template, redirect, url_for, g
from app.auth import login_required
from app.db import get_db

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def root():
    """Application root: always route visitors to authentication portal."""
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def index():
    """Render the central dashboard with live aggregate metrics and recent records from SQLite."""
    db = get_db()

    # 1. Metric: Total active patients
    active_patients_count = db.execute(
        "SELECT COUNT(*) FROM Patient WHERE is_active = 1"
    ).fetchone()[0]

    # Total registered patients (including inactive)
    total_patients_count = db.execute(
        "SELECT COUNT(*) FROM Patient"
    ).fetchone()[0]

    # 2. Metric: Total active doctors
    active_doctors_count = db.execute(
        "SELECT COUNT(*) FROM Doctor WHERE is_active = 1"
    ).fetchone()[0]

    # 3. Metric: Total appointments and scheduled count
    total_appointments_count = db.execute(
        "SELECT COUNT(*) FROM Appointment"
    ).fetchone()[0]

    scheduled_appointments_count = db.execute(
        "SELECT COUNT(*) FROM Appointment WHERE Status = 'Scheduled'"
    ).fetchone()[0]

    # 4. Metric: Total bills and total revenue amount
    bill_stats = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(B_Amount), 0.0) FROM Bill"
    ).fetchone()
    total_bills_count = bill_stats[0]
    total_revenue = bill_stats[1]

    # 5. Recent / Upcoming Appointments with Patient & Doctor JOINs
    recent_appointments = db.execute(
        """
        SELECT 
            a.Appointment_ID,
            a.A_Date,
            a.A_Time,
            a.Reason,
            a.Duration_Min,
            a.Status,
            p.Patient_id,
            p.P_Name AS Patient_Name,
            d.Doctor_ID,
            d.D_Name AS Doctor_Name
        FROM Appointment a
        JOIN Patient p ON a.Patient_id = p.Patient_id
        JOIN Doctor d ON a.Doctor_ID = d.Doctor_ID
        ORDER BY a.A_Date DESC, a.A_Time DESC
        LIMIT 5
        """
    ).fetchall()

    # 6. Recently Created Bills with Patient JOIN
    recent_bills = db.execute(
        """
        SELECT 
            b.Bill_ID,
            b.B_Date,
            b.B_Amount,
            b.Pay_Mode,
            b.Created_At,
            p.Patient_id,
            p.P_Name AS Patient_Name
        FROM Bill b
        JOIN Patient p ON b.Patient_id = p.Patient_id
        ORDER BY b.Bill_ID DESC
        LIMIT 5
        """
    ).fetchall()

    # 7. Live analytics: Monthly Appointment Volume (12 months)
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_data = {f"{i:02d}": 0 for i in range(1, 13)}
    monthly_rows = db.execute(
        "SELECT substr(A_Date, 6, 2) as m, COUNT(*) as cnt FROM Appointment GROUP BY m ORDER BY m"
    ).fetchall()
    for row in monthly_rows:
        if row["m"] in monthly_data:
            monthly_data[row["m"]] = row["cnt"]
    trend_labels = month_names
    trend_counts = [monthly_data[f"{i:02d}"] for i in range(1, 13)]

    # 8. Live analytics: Settlement breakdown by payment mode
    pay_rows = db.execute(
        "SELECT Pay_Mode, COUNT(*) as cnt FROM Bill GROUP BY Pay_Mode ORDER BY cnt DESC"
    ).fetchall()
    settlement_labels = [r["Pay_Mode"] for r in pay_rows]
    settlement_counts = [r["cnt"] for r in pay_rows]

    return render_template(
        "dashboard.html",
        active_patients_count=active_patients_count,
        total_patients_count=total_patients_count,
        active_doctors_count=active_doctors_count,
        total_appointments_count=total_appointments_count,
        scheduled_appointments_count=scheduled_appointments_count,
        total_bills_count=total_bills_count,
        total_revenue=total_revenue,
        recent_appointments=recent_appointments,
        recent_bills=recent_bills,
        trend_labels=trend_labels,
        trend_counts=trend_counts,
        settlement_labels=settlement_labels,
        settlement_counts=settlement_counts,
    )
