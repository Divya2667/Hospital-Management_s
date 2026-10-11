import pytest
from werkzeug.security import generate_password_hash
from app.db import get_db


def login_admin(app, client):
    """Helper to authenticate a staff/admin user."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("admin_patient_test", generate_password_hash("pass123"), "Admin"),
        )
        db.commit()

    client.post("/auth/login", data={"username": "admin_patient_test", "password": "pass123"})


def test_patient_routes_require_authentication(client):
    """All patient routes must redirect unauthenticated visitors."""
    assert client.get("/patients/").status_code == 302
    assert client.get("/patients/create").status_code == 302
    assert client.get("/patients/1").status_code == 302
    assert client.get("/patients/1/edit").status_code == 302
    assert client.post("/patients/1/toggle-status").status_code == 302
    assert client.post("/patients/1/delete").status_code == 302


def test_patient_create_validation_and_success(app, client):
    """Test server-side validation and successful creation of a patient."""
    login_admin(app, client)

    # 1. Validation failure: empty name
    res = client.post(
        "/patients/create",
        data={"name": "", "age": "25", "gender": "Male", "blood_group": "O+"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Patient name is required." in res.data

    # 2. Validation failure: age out of range
    res = client.post(
        "/patients/create",
        data={"name": "Old Person", "age": "150", "gender": "Male", "blood_group": "O+"},
        follow_redirects=True,
    )
    assert b"Patient age must be between 0 and 120." in res.data

    # 3. Validation failure: invalid gender
    res = client.post(
        "/patients/create",
        data={"name": "Test Person", "age": "30", "gender": "Unknown", "blood_group": "O+"},
        follow_redirects=True,
    )
    assert b"Gender must be one of: Male, Female, Other." in res.data

    # 4. Validation failure: invalid blood group
    res = client.post(
        "/patients/create",
        data={"name": "Test Person", "age": "30", "gender": "Female", "blood_group": "X+"},
        follow_redirects=True,
    )
    assert b"Blood group must be one of:" in res.data

    # 5. Successful registration
    success_res = client.post(
        "/patients/create",
        data={"name": "Samantha Wright", "age": "29", "gender": "Female", "blood_group": "B+"},
        follow_redirects=True,
    )
    assert success_res.status_code == 200
    assert b"Samantha Wright" in success_res.data
    assert b"29 Years" in success_res.data
    assert b"B+" in success_res.data

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT * FROM Patient WHERE P_Name = 'Samantha Wright'").fetchone()
        assert patient is not None
        assert patient["P_Age"] == 29
        assert patient["P_Gender"] == "Female"
        assert patient["Blood_Group"] == "B+"
        assert patient["is_active"] == 1


def test_patient_edit(app, client):
    """Test editing an existing patient's details."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Robert Fox', 50, 'Male', 'A+', 1)"
        )
        patient_id = cur.lastrowid
        db.commit()

    # GET edit form
    get_res = client.get(f"/patients/{patient_id}/edit")
    assert get_res.status_code == 200
    assert b"Robert Fox" in get_res.data

    # POST updated details
    post_res = client.post(
        f"/patients/{patient_id}/edit",
        data={"name": "Robert Fox Jr.", "age": "51", "gender": "Male", "blood_group": "AB+"},
        follow_redirects=True,
    )
    assert post_res.status_code == 200
    assert b"Robert Fox Jr." in post_res.data
    assert b"51 Years" in post_res.data
    assert b"AB+" in post_res.data

    with app.app_context():
        db = get_db()
        updated = db.execute("SELECT * FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()
        assert updated["P_Name"] == "Robert Fox Jr."
        assert updated["P_Age"] == 51
        assert updated["Blood_Group"] == "AB+"


def test_patient_search_and_status_filtering(app, client):
    """Test search by name, search by ID, and active/inactive status filtering."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Alice Johnson', 25, 'Female', 'O+', 1)")
        db.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Bob Smith', 40, 'Male', 'A-', 0)")
        db.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Alicia Keys', 35, 'Female', 'B+', 1)")
        db.commit()

    # Search by partial name "Alic" -> should find Alice and Alicia, but not Bob
    search_res = client.get("/patients/?search=Alic")
    assert b"Alice Johnson" in search_res.data
    assert b"Alicia Keys" in search_res.data
    assert b"Bob Smith" not in search_res.data

    # Filter active only -> Alice and Alicia, no Bob
    active_res = client.get("/patients/?status=active")
    assert b"Alice Johnson" in active_res.data
    assert b"Bob Smith" not in active_res.data

    # Filter inactive only -> Bob only
    inactive_res = client.get("/patients/?status=inactive")
    assert b"Bob Smith" in inactive_res.data
    assert b"Alice Johnson" not in inactive_res.data


def test_patient_deactivation_toggle(app, client):
    """Test toggling a patient active and inactive."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Mark Otto', 33, 'Male', 'O-', 1)")
        patient_id = cur.lastrowid
        db.commit()

    # Deactivate
    toggle_res = client.post(f"/patients/{patient_id}/toggle-status", follow_redirects=True)
    assert toggle_res.status_code == 200
    assert b"has been deactivated." in toggle_res.data

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT is_active FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()[0] == 0

    # Reactivate
    toggle_res2 = client.post(f"/patients/{patient_id}/toggle-status", follow_redirects=True)
    assert toggle_res2.status_code == 200
    assert b"has been reactivated." in toggle_res2.data

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT is_active FROM Patient WHERE Patient_id = ?", (patient_id,)).fetchone()[0] == 1


def test_patient_detail_appointment_and_billing_history(app, client):
    """Test patient detail view displays complete appointment history, bills, and totals."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()

        # Insert Patient
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Clara Oswald', 26, 'Female', 'AB+', 1)")
        p_id = cur.lastrowid

        # Insert Doctor
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Who', 'MD Time Lord', 900, '555-TARDIS', 1)")
        d_id = cur.lastrowid

        # Insert Appointment
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, '2026-10-20', '09:30', 'Tachyon Exposure Check', 30, 'Scheduled')""",
            (p_id, d_id),
        )

        # Insert Bills
        cur.execute("INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, '2026-10-18', 350.00, 'Insurance')", (p_id,))
        cur.execute("INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, '2026-10-20', 120.50, 'Card')", (p_id,))
        db.commit()

    detail_res = client.get(f"/patients/{p_id}")
    assert detail_res.status_code == 200
    # Appointment verified
    assert b"Dr. Who" in detail_res.data
    assert b"Tachyon Exposure Check" in detail_res.data
    assert b"2026-10-20" in detail_res.data
    # Bills and total verified ($350 + $120.50 = $470.50)
    assert b"$350.00" in detail_res.data
    assert b"$120.50" in detail_res.data
    assert b"$470.50" in detail_res.data


def test_patient_safe_deletion_prevented_with_records(app, client):
    """Safe deletion must block deleting a patient with existing appointments or bills."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Protected Patient', 45, 'Male', 'O+', 1)")
        p_id = cur.lastrowid
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Care', 'MBBS', 5, '555-001', 1)")
        d_id = cur.lastrowid
        cur.execute("INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason) VALUES (?, ?, '2026-10-22', '11:00', 'Checkup')", (p_id, d_id))
        db.commit()

    # Attempt deletion of patient who has appointment
    del_res = client.post(f"/patients/{p_id}/delete", follow_redirects=True)
    assert del_res.status_code == 200
    assert b"Cannot delete Patient" in del_res.data
    assert b"Please deactivate the patient instead" in del_res.data

    # Verify patient still exists in database
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT * FROM Patient WHERE Patient_id = ?", (p_id,)).fetchone() is not None


def test_patient_deletion_success_standalone(app, client):
    """Deleting a patient without any appointment or billing records should succeed."""
    login_admin(app, client)

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Disposable Patient', 22, 'Other', 'A+', 1)")
        p_id = cur.lastrowid
        db.commit()

    # Delete standalone patient
    del_res = client.post(f"/patients/{p_id}/delete", follow_redirects=True)
    assert del_res.status_code == 200
    assert b"was successfully deleted." in del_res.data

    # Verify patient is gone
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT * FROM Patient WHERE Patient_id = ?", (p_id,)).fetchone() is None
