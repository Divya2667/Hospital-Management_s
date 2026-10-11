import pytest
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
from app.db import get_db


def login_admin(app, client):
    """Helper to authenticate admin user."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("admin_appt_tester", generate_password_hash("pass123"), "Admin"),
        )
        db.commit()

    client.post("/auth/login", data={"username": "admin_appt_tester", "password": "pass123"})


def setup_sample_patient_and_doctor(app):
    """Helper to create patient and doctors in database."""
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Peter Parker', 22, 'Male', 'O+', 1)")
        patient_id = cur.lastrowid

        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Strange', 'MD Sorcery', 15, '555-111-2222', 1)")
        doc_strange_id = cur.lastrowid

        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Banner', 'MD Oncology', 18, '555-333-4444', 1)")
        doc_banner_id = cur.lastrowid

        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Offduty', 'MBBS', 5, '555-999-0000', 0)")
        doc_offduty_id = cur.lastrowid

        db.commit()
        return patient_id, doc_strange_id, doc_banner_id, doc_offduty_id


def test_appointment_routes_require_authentication(client):
    """All appointment endpoints must redirect unauthenticated visitors."""
    assert client.get("/appointments/").status_code == 302
    assert client.get("/appointments/create").status_code == 302
    assert client.get("/appointments/1").status_code == 302
    assert client.get("/appointments/1/edit").status_code == 302
    assert client.post("/appointments/1/cancel").status_code == 302
    assert client.post("/appointments/1/complete").status_code == 302


def test_appointment_validation_rules(app, client):
    """Test validation of patient, active doctor, past date, clinic hours, and empty reason."""
    login_admin(app, client)
    p_id, d_strange, d_banner, d_offduty = setup_sample_patient_and_doctor(app)
    future_date = (date.today() + timedelta(days=5)).isoformat()
    past_date = (date.today() - timedelta(days=2)).isoformat()

    # 1. Non-existent patient
    res = client.post(
        "/appointments/create",
        data={"patient_id": "9999", "doctor_id": str(d_strange), "date": future_date, "time": "10:00", "reason": "Checkup"},
        follow_redirects=True,
    )
    assert b"The selected patient does not exist." in res.data

    # 2. Inactive / off-duty doctor
    res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_offduty), "date": future_date, "time": "10:00", "reason": "Checkup"},
        follow_redirects=True,
    )
    assert b"is currently inactive/off-duty" in res.data

    # 3. Past date
    res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": past_date, "time": "10:00", "reason": "Checkup"},
        follow_redirects=True,
    )
    assert b"Appointment date cannot be in the past." in res.data

    # 4. Before clinic opening hours (08:30 < 09:00)
    res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": future_date, "time": "08:30", "reason": "Checkup"},
        follow_redirects=True,
    )
    assert b"cannot be earlier than clinic opening hours" in res.data

    # 5. Extends beyond clinic closing hours (16:45 + 30m = 17:15 > 17:00)
    res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": future_date, "time": "16:45", "duration": "30", "reason": "Checkup"},
        follow_redirects=True,
    )
    assert b"extends beyond clinic closing hours" in res.data

    # 6. Empty reason
    res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": future_date, "time": "10:00", "reason": ""},
        follow_redirects=True,
    )
    assert b"Please enter the clinical reason" in res.data


def test_doctor_appointment_overlap_conflict_prevention(app, client):
    """Comprehensive test for scheduling conflict detection:
       - Exact overlap: REJECT
       - Partial overlap: REJECT
       - Non-overlapping consecutive slot: ALLOW
       - Different doctor at same time: ALLOW
    """
    login_admin(app, client)
    p_id, d_strange, d_banner, _ = setup_sample_patient_and_doctor(app)
    appt_date = (date.today() + timedelta(days=3)).isoformat()

    # 1. Book base appointment: 10:00 - 10:30 with Dr. Strange
    base_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "10:00", "duration": "30", "reason": "Initial Consult"},
        follow_redirects=True,
    )
    assert base_res.status_code == 200
    assert b"scheduled successfully" in base_res.data
    assert b"Initial Consult" in base_res.data

    # 2. Attempt exact overlapping slot (10:00 - 10:30) with Dr. Strange -> MUST REJECT
    exact_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "10:00", "duration": "30", "reason": "Duplicate Slot"},
        follow_redirects=True,
    )
    assert b"Scheduling Conflict: Dr. Strange already has an appointment scheduled from 10:00 to 10:30" in exact_res.data

    # 3. Attempt partial overlapping slot (10:15 - 10:45) with Dr. Strange -> MUST REJECT
    partial_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "10:15", "duration": "30", "reason": "Partial Overlap"},
        follow_redirects=True,
    )
    assert b"Scheduling Conflict: Dr. Strange already has an appointment scheduled from 10:00 to 10:30" in partial_res.data

    # 4. Attempt consecutive non-overlapping slot (10:30 - 11:00) with Dr. Strange -> MUST ALLOW
    consec_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "10:30", "duration": "30", "reason": "Consecutive Followup"},
        follow_redirects=True,
    )
    assert consec_res.status_code == 200
    assert b"scheduled successfully" in consec_res.data
    assert b"Consecutive Followup" in consec_res.data

    # 5. Attempt slot at same time (10:00 - 10:30) with DIFFERENT DOCTOR (Dr. Banner) -> MUST ALLOW
    other_doc_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_banner), "date": appt_date, "time": "10:00", "duration": "30", "reason": "Different Doctor Consult"},
        follow_redirects=True,
    )
    assert other_doc_res.status_code == 200
    assert b"scheduled successfully" in other_doc_res.data
    assert b"Different Doctor Consult" in other_doc_res.data


def test_appointment_cancellation_releases_slot(app, client):
    """Cancelled appointments must no longer block scheduling."""
    login_admin(app, client)
    p_id, d_strange, _, _ = setup_sample_patient_and_doctor(app)
    appt_date = (date.today() + timedelta(days=4)).isoformat()

    # 1. Book appointment at 11:00 - 11:30
    res1 = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "11:00", "duration": "30", "reason": "Will be cancelled"},
    )
    with app.app_context():
        db = get_db()
        appt_id = db.execute("SELECT Appointment_ID FROM Appointment WHERE Reason = 'Will be cancelled'").fetchone()[0]

    # 2. Cancel the appointment
    cancel_res = client.post(f"/appointments/{appt_id}/cancel", follow_redirects=True)
    assert cancel_res.status_code == 200
    assert b"has been cancelled" in cancel_res.data

    with app.app_context():
        db = get_db()
        status = db.execute("SELECT Status FROM Appointment WHERE Appointment_ID = ?", (appt_id,)).fetchone()[0]
        assert status == "Cancelled"

    # 3. Book NEW appointment for the SAME doctor, SAME date, and SAME time (11:00 - 11:30) -> MUST SUCCEED
    rebook_res = client.post(
        "/appointments/create",
        data={"patient_id": str(p_id), "doctor_id": str(d_strange), "date": appt_date, "time": "11:00", "duration": "30", "reason": "New Patient Replaced Slot"},
        follow_redirects=True,
    )
    assert rebook_res.status_code == 200
    assert b"scheduled successfully" in rebook_res.data
    assert b"New Patient Replaced Slot" in rebook_res.data


def test_appointment_edit_with_self_exclusion(app, client):
    """When editing an appointment, it must exclude itself from the conflict check."""
    login_admin(app, client)
    p_id, d_strange, _, _ = setup_sample_patient_and_doctor(app)
    appt_date = (date.today() + timedelta(days=7)).isoformat()

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, ?, '14:00', 'Original Reason', 30, 'Scheduled')""",
            (p_id, d_strange, appt_date),
        )
        appt_id = cur.lastrowid
        db.commit()

    # 1. Edit details keeping the exact same time -> Must NOT report a conflict against itself
    edit_res = client.post(
        f"/appointments/{appt_id}/edit",
        data={
            "doctor_id": str(d_strange),
            "date": appt_date,
            "time": "14:00",
            "duration": "30",
            "reason": "Updated Reason Without Conflict",
            "status": "Scheduled",
        },
        follow_redirects=True,
    )
    assert edit_res.status_code == 200
    assert b"Updated Reason Without Conflict" in edit_res.data

    with app.app_context():
        db = get_db()
        row = db.execute("SELECT Reason FROM Appointment WHERE Appointment_ID = ?", (appt_id,)).fetchone()
        assert row["Reason"] == "Updated Reason Without Conflict"


def test_appointment_status_complete(app, client):
    """Marking an appointment as completed updates its status in SQLite."""
    login_admin(app, client)
    p_id, d_strange, _, _ = setup_sample_patient_and_doctor(app)
    appt_date = (date.today() + timedelta(days=2)).isoformat()

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, ?, '15:00', 'Completion Test', 30, 'Scheduled')""",
            (p_id, d_strange, appt_date),
        )
        appt_id = cur.lastrowid
        db.commit()

    complete_res = client.post(f"/appointments/{appt_id}/complete", follow_redirects=True)
    assert complete_res.status_code == 200
    assert b"marked as completed." in complete_res.data

    with app.app_context():
        db = get_db()
        status = db.execute("SELECT Status FROM Appointment WHERE Appointment_ID = ?", (appt_id,)).fetchone()[0]
        assert status == "Completed"


def test_appointment_search_and_filters(app, client):
    """Test multi-attribute filters (Doctor, Patient, Date, Status, Search)."""
    login_admin(app, client)
    p_id, d_strange, d_banner, _ = setup_sample_patient_and_doctor(app)
    date1 = (date.today() + timedelta(days=10)).isoformat()
    date2 = (date.today() + timedelta(days=11)).isoformat()

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status) VALUES (?, ?, ?, '09:30', 'Headache Evaluation', 30, 'Scheduled')",
            (p_id, d_strange, date1),
        )
        db.execute(
            "INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status) VALUES (?, ?, ?, '11:00', 'Radiation Therapy Check', 30, 'Completed')",
            (p_id, d_banner, date2),
        )
        db.commit()

    # Search by keyword in reason "Headache"
    res_search = client.get("/appointments/?search=Headache")
    assert b"Headache Evaluation" in res_search.data
    assert b"Radiation Therapy Check" not in res_search.data

    # Filter by Doctor (Dr. Banner)
    res_doc = client.get(f"/appointments/?doctor_id={d_banner}")
    assert b"Radiation Therapy Check" in res_doc.data
    assert b"Headache Evaluation" not in res_doc.data

    # Filter by Status (Completed)
    res_status = client.get("/appointments/?status=Completed")
    assert b"Radiation Therapy Check" in res_status.data
    assert b"Headache Evaluation" not in res_status.data
