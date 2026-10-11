import pytest
from werkzeug.security import generate_password_hash
from app.db import get_db


def create_authenticated_user(app, client, username="admin_user", role="Admin"):
    """Helper to register and login a user for dashboard testing."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            (username, generate_password_hash("pass123"), role),
        )
        db.commit()

    client.post("/auth/login", data={"username": username, "password": "pass123"})


def test_dashboard_unauthenticated_redirect(client):
    """Unauthenticated users must be redirected to login."""
    res = client.get("/dashboard")
    assert res.status_code == 302
    assert "/auth/login?next=/dashboard" in res.headers["Location"]


def test_dashboard_authenticated_empty_state(app, client):
    """Authenticated user sees dashboard structure and empty state counts of 0."""
    create_authenticated_user(app, client, "doc_dan", "Doctor")
    response = client.get("/dashboard")
    assert response.status_code == 200

    # Verification of base layout elements
    assert b"Hospital Operations Dashboard" in response.data
    assert b"doc_dan" in response.data
    assert b"Doctor" in response.data
    assert b"sidebar-wrapper" in response.data
    assert b"sidebarToggle" in response.data
    assert b"btn-logout" in response.data

    # Verification of summary metric cards and zero counts
    assert b'id="val-patients-count">0</div>' in response.data
    assert b'id="val-doctors-count">0</div>' in response.data
    assert b'id="val-appointments-count">0</div>' in response.data
    assert b'id="val-bills-count">0</div>' in response.data

    # Verification of empty state messages
    assert b"No Appointments Yet" in response.data
    assert b"No Billing Records Yet" in response.data


def test_dashboard_dynamic_aggregations_and_joins(app, client):
    """Verify dynamic SQLite aggregation counts and recent appointment/bill table rows with JOINs."""
    create_authenticated_user(app, client, "hospital_admin", "Admin")

    with app.app_context():
        db = get_db()
        cur = db.cursor()

        # Insert Patients (2 active, 1 inactive)
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Emily Clark', 32, 'Female', 'O+', 1)")
        p1 = cur.lastrowid
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('David Miller', 45, 'Male', 'A+', 1)")
        p2 = cur.lastrowid
        cur.execute("INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group, is_active) VALUES ('Inactive Patient', 60, 'Male', 'B-', 0)")
        p3 = cur.lastrowid

        # Insert Doctors (2 active, 1 inactive)
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Gregory House', 'MD Diagnostics', 15, '555-101', 1)")
        d1 = cur.lastrowid
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Allison Cameron', 'MD Immunology', 8, '555-102', 1)")
        d2 = cur.lastrowid
        cur.execute("INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone, is_active) VALUES ('Dr. Retired', 'MBBS', 30, '555-103', 0)")
        d3 = cur.lastrowid

        # Insert Appointments (1 Scheduled, 1 Completed)
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, '2026-10-15', '10:00', 'Cardiac Consultation', 30, 'Scheduled')""",
            (p1, d1),
        )
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, '2026-10-14', '14:30', 'Routine Followup', 30, 'Completed')""",
            (p2, d2),
        )

        # Insert Bills ($150.00 and $250.50 -> Total $400.50)
        cur.execute("INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, '2026-10-14', 150.00, 'Cash')", (p1,))
        cur.execute("INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, '2026-10-15', 250.50, 'UPI')", (p2,))

        db.commit()

    # Query dashboard
    response = client.get("/dashboard")
    assert response.status_code == 200

    # 1. Active Patients = 2, Total = 3
    assert b'id="val-patients-count">2</div>' in response.data
    assert b"3 total registered" in response.data

    # 2. Active Doctors = 2
    assert b'id="val-doctors-count">2</div>' in response.data

    # 3. Appointments = 2 (1 scheduled)
    assert b'id="val-appointments-count">2</div>' in response.data
    assert b"1 scheduled upcoming" in response.data

    # 4. Total Bills = 2, Total Revenue = $400.50
    assert b'id="val-bills-count">2</div>' in response.data
    assert b"$400.50" in response.data

    # 5. Appointments table JOIN verification
    assert b"Emily Clark" in response.data
    assert b"Dr. Gregory House" in response.data
    assert b"Cardiac Consultation" in response.data
    assert b"David Miller" in response.data
    assert b"Dr. Allison Cameron" in response.data
    assert b"Scheduled" in response.data
    assert b"Completed" in response.data

    # 6. Bills table JOIN verification
    assert b"UPI" in response.data
    assert b"Cash" in response.data
    assert b"$150.00" in response.data
    assert b"$250.50" in response.data


def test_clickable_cards_and_navigation_links(app, client):
    """Summary cards must be clickable links leading to corresponding management modules."""
    create_authenticated_user(app, client, "nav_tester", "Admin")
    response = client.get("/dashboard")
    assert response.status_code == 200

    # Verify metric cards are clickable anchors
    assert b'id="card-metric-patients"' in response.data
    assert b'id="card-metric-doctors"' in response.data
    assert b'id="card-metric-appointments"' in response.data
    assert b'id="card-metric-billing"' in response.data
