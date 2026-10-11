import pytest
from werkzeug.security import generate_password_hash
from app.db import get_db


def login_admin(app, client):
    """Helper to authenticate a staff/admin user."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("admin_doctor_test", generate_password_hash("pass123"), "Admin"),
        )
        db.commit()

    client.post("/auth/login", data={"username": "admin_doctor_test", "password": "pass123"})


def test_doctor_routes_require_authentication(client):
    """All doctor management endpoints must redirect unauthenticated visitors."""
    assert client.get("/doctors/").status_code == 302
    assert client.get("/doctors/create").status_code == 302
    assert client.get("/doctors/1").status_code == 302
    assert client.get("/doctors/1/edit").status_code == 302
    assert client.post("/doctors/1/toggle-status").status_code == 302
    assert client.post("/doctors/1/delete").status_code == 302


def test_doctor_create_validation_and_duplicate_phone(app, client):
    """Test doctor field validation, duplicate phone rejection, and successful insertion."""
    login_admin(app, client)

    # 1. Validation failure: empty name
    res = client.post(
        "/doctors/create",
        data={"name": "", "qualification": "MD", "experience": "5", "phone": "555-1234"},
        follow_redirects=True,
    )
    assert b"Doctor name is required." in res.data

    # 2. Validation failure: empty qualification
    res = client.post(
        "/doctors/create",
        data={"name": "Dr. Strange", "qualification": "", "experience": "5", "phone": "555-1234"},
        follow_redirects=True,
    )
    assert b"Doctor qualification is required." in res.data

    # 3. Validation failure: negative experience
    res = client.post(
        "/doctors/create",
        data={"name": "Dr. Strange", "qualification": "MD", "experience": "-1", "phone": "555-1234"},
        follow_redirects=True,
    )
    assert b"Experience cannot be negative." in res.data

    # 4. Validation failure: invalid/too short phone
    res = client.post(
        "/doctors/create",
        data={"name": "Dr. Strange", "qualification": "MD", "experience": "5", "phone": "123"},
        follow_redirects=True,
    )
    assert b"Phone number must contain between 7 and 15 digits." in res.data

    # 5. Successful doctor creation
    success_res = client.post(
        "/doctors/create",
        data={
            "name": "Dr. Leonard McCoy",
            "qualification": "Chief Medical Officer, MD",
            "experience": "20",
            "phone": "555-888-9999",
        },
        follow_redirects=True,
    )
    assert success_res.status_code == 200
    assert b"Dr. Leonard McCoy" in success_res.data
    assert b"Chief Medical Officer, MD" in success_res.data
    assert b"20 Years" in success_res.data

    # 6. Duplicate phone rejection
    dup_res = client.post(
        "/doctors/create",
        data={
            "name": "Dr. Impostor",
            "qualification": "MBBS",
            "experience": "2",
            "phone": "555-888-9999",
        },
        follow_redirects=True,
    )
    assert b"Phone number is already associated with" in dup_res.data


def test_doctor_edit(app, client):
    """Test editing doctor credentials and experience."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Beverly Crusher', 'MD Neuro', 15, '555-111-2222', 1)"
        )
        doctor_id = cur.lastrowid
        db.commit()

    # GET edit form
    get_res = client.get(f"/doctors/{doctor_id}/edit")
    assert get_res.status_code == 200
    assert b"Dr. Beverly Crusher" in get_res.data

    # POST updated details
    post_res = client.post(
        f"/doctors/{doctor_id}/edit",
        data={
            "name": "Dr. Beverly Crusher",
            "qualification": "MD Neurology, CMO",
            "experience": "16",
            "phone": "555-111-2222",
        },
        follow_redirects=True,
    )
    assert post_res.status_code == 200
    assert b"MD Neurology, CMO" in post_res.data
    assert b"16 Years" in post_res.data

    with app.app_context():
        db = get_db()
        updated = db.execute("SELECT * FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()
        assert updated["D_Qualification"] == "MD Neurology, CMO"
        assert updated["Experience"] == 16


def test_doctor_search_and_status_filtering(app, client):
    """Test searching doctors by name or qualification and filtering by active/inactive status."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Sanjay Gupta', 'MD Neurosurgery', 18, '555-301-0001', 1)")
        db.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Atul Gawande', 'MD General Surgery', 22, '555-301-0002', 0)")
        db.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Paul Farmer', 'MD Infectious Disease', 25, '555-301-0003', 1)")
        db.commit()

    # Search by qualification "Neuro"
    search_res = client.get("/doctors/?search=Neuro")
    assert b"Dr. Sanjay Gupta" in search_res.data
    assert b"Dr. Atul Gawande" not in search_res.data

    # Filter active only -> Gupta and Farmer, not Gawande
    active_res = client.get("/doctors/?status=active")
    assert b"Dr. Sanjay Gupta" in active_res.data
    assert b"Dr. Paul Farmer" in active_res.data
    assert b"Dr. Atul Gawande" not in active_res.data

    # Filter inactive only -> Gawande
    inactive_res = client.get("/doctors/?status=inactive")
    assert b"Dr. Atul Gawande" in inactive_res.data
    assert b"Dr. Sanjay Gupta" not in inactive_res.data


def test_doctor_deactivation_toggle(app, client):
    """Test toggling doctor on-duty and off-duty status."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Toggle Test', 'MBBS', 6, '555-444-5555', 1)")
        doctor_id = cur.lastrowid
        db.commit()

    # Deactivate (Set off-duty)
    toggle_res = client.post(f"/doctors/{doctor_id}/toggle-status", follow_redirects=True)
    assert toggle_res.status_code == 200
    assert b"deactivated (off-duty)" in toggle_res.data

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT is_active FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()[0] == 0

    # Reactivate (Set on-duty)
    toggle_res2 = client.post(f"/doctors/{doctor_id}/toggle-status", follow_redirects=True)
    assert toggle_res2.status_code == 200
    assert b"reactivated (on-duty)" in toggle_res2.data

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT is_active FROM Doctor WHERE Doctor_ID = ?", (doctor_id,)).fetchone()[0] == 1


def test_doctor_assigned_appointments_history(app, client):
    """Test doctor detail view displays their clinical appointments schedule."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Rose Tyler', 21, 'Female', 'O+', 1)")
        p_id = cur.lastrowid

        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. John Watson', 'MD Military Surgery', 12, '555-221-BAKR', 1)")
        d_id = cur.lastrowid

        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, '2026-10-25', '14:00', 'Shoulder Wound Assessment', 30, 'Scheduled')""",
            (p_id, d_id),
        )
        db.commit()

    res = client.get(f"/doctors/{d_id}")
    assert res.status_code == 200
    assert b"Dr. John Watson" in res.data
    assert b"Rose Tyler" in res.data
    assert b"Shoulder Wound Assessment" in res.data
    assert b"14:00" in res.data
    assert b"1 Appointments" in res.data


def test_doctor_safe_deletion_prevented_with_appointments(app, client):
    """Safe deletion must prevent deleting doctors who have historical appointment records."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Patient One', 30, 'Male', 'A+', 1)")
        p_id = cur.lastrowid

        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Essential', 'MD Cardiology', 20, '555-900-1111', 1)")
        d_id = cur.lastrowid

        cur.execute("INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason) VALUES (?, ?, '2026-10-26', '10:00', 'ECG Followup')", (p_id, d_id))
        db.commit()

    # Attempt deletion
    del_res = client.post(f"/doctors/{d_id}/delete", follow_redirects=True)
    assert del_res.status_code == 200
    assert b"Cannot delete Doctor" in del_res.data
    assert b"Please deactivate the doctor instead" in del_res.data

    # Verify doctor still exists in SQLite
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT * FROM Doctor WHERE Doctor_ID = ?", (d_id,)).fetchone() is not None


def test_doctor_deletion_success_standalone(app, client):
    """Deleting a doctor with zero appointments must succeed."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Temporary', 'MBBS', 1, '555-000-9999', 1)")
        d_id = cur.lastrowid
        db.commit()

    del_res = client.post(f"/doctors/{d_id}/delete", follow_redirects=True)
    assert del_res.status_code == 200
    assert b"was successfully deleted." in del_res.data

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT * FROM Doctor WHERE Doctor_ID = ?", (d_id,)).fetchone() is None
