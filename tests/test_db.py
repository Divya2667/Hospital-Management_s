import sqlite3
import pytest
from app.db import get_db, close_db


def test_get_close_db(app):
    """Test that get_db returns the same connection in context and closes on teardown."""
    with app.app_context():
        db = get_db()
        assert db is get_db()
        # Verify foreign keys are enabled on connection
        fk_status = db.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk_status == 1

    # Context exited, connection should be closed
    with pytest.raises(sqlite3.ProgrammingError) as exc_info:
        db.execute("SELECT 1")
    assert "closed" in str(exc_info.value).lower()


def test_init_db_command(runner, monkeypatch):
    """Test the flask init-db CLI command."""
    class Recorder:
        called = False

    def fake_init_db():
        Recorder.called = True

    monkeypatch.setattr("app.db.init_db", fake_init_db)
    result = runner.invoke(args=["init-db"])
    assert "Initialized the SQLite database successfully." in result.output
    assert Recorder.called is True


def test_patient_constraints(app):
    """Test Patient check constraints for Age, Gender, and Blood Group."""
    with app.app_context():
        db = get_db()
        # Valid insert
        db.execute(
            "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
            ("John Doe", 35, "Male", "O+"),
        )
        db.commit()

        # Invalid Age (< 0)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
                ("Invalid Age", -5, "Male", "O+"),
            )

        # Invalid Gender
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
                ("Invalid Gender", 25, "Alien", "O+"),
            )

        # Invalid Blood Group
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
                ("Invalid BG", 25, "Male", "Z+"),
            )


def test_doctor_constraints(app):
    """Test Doctor constraints."""
    with app.app_context():
        db = get_db()
        # Valid insert
        db.execute(
            "INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone) VALUES (?, ?, ?, ?)",
            ("Dr. Smith", "MD Cardiology", 12, "9876543210"),
        )
        db.commit()

        # Invalid Experience (< 0)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone) VALUES (?, ?, ?, ?)",
                ("Dr. Invalid", "MBBS", -1, "9876543210"),
            )


def test_appointment_foreign_keys_and_restrictions(app):
    """Test Appointment foreign keys to Patient and Doctor and ON DELETE RESTRICT behavior."""
    with app.app_context():
        db = get_db()
        # Setup valid Patient & Doctor
        cur = db.cursor()
        cur.execute(
            "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
            ("Alice", 28, "Female", "A+"),
        )
        patient_id = cur.lastrowid

        cur.execute(
            "INSERT INTO Doctor (D_Name, D_Qualification, Experience, D_Phone) VALUES (?, ?, ?, ?)",
            ("Dr. Bob", "MD Neurology", 8, "9988776655"),
        )
        doctor_id = cur.lastrowid
        db.commit()

        # Valid Appointment
        cur.execute(
            """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, doctor_id, "2026-10-15", "10:00", "Regular Checkup", 30, "Scheduled"),
        )
        db.commit()

        # Foreign Key Violation: Non-existent Patient
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (9999, doctor_id, "2026-10-15", "11:00", "Consultation"),
            )

        # Foreign Key Violation: Non-existent Doctor
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO Appointment (Patient_id, Doctor_ID, A_Date, A_Time, Reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (patient_id, 9999, "2026-10-15", "11:00", "Consultation"),
            )

        # ON DELETE RESTRICT: Cannot delete Patient while appointment exists
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM Patient WHERE Patient_id = ?", (patient_id,))

        # ON DELETE RESTRICT: Cannot delete Doctor while appointment exists
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM Doctor WHERE Doctor_ID = ?", (doctor_id,))


def test_bill_foreign_keys_and_constraints(app):
    """Test Bill foreign key to Patient, check constraints, and ON DELETE RESTRICT."""
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES (?, ?, ?, ?)",
            ("Charlie", 45, "Male", "B+"),
        )
        patient_id = cur.lastrowid
        db.commit()

        # Valid Bill
        cur.execute(
            "INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, ?, ?, ?)",
            (patient_id, "2026-10-12", 1500.50, "UPI"),
        )
        db.commit()

        # Invalid: Non-existent Patient
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, ?, ?, ?)",
                (9999, "2026-10-12", 500.00, "Cash"),
            )

        # Invalid: Non-positive Amount
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, ?, ?, ?)",
                (patient_id, "2026-10-12", 0.00, "Cash"),
            )

        # Invalid: Unsupported Pay Mode
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode) VALUES (?, ?, ?, ?)",
                (patient_id, "2026-10-12", 500.00, "Bitcoin"),
            )

        # ON DELETE RESTRICT: Cannot delete Patient with bill
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM Patient WHERE Patient_id = ?", (patient_id,))


def test_user_unique_and_role_constraints(app):
    """Test User unique username and role constraints."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("admin1", "scrypt:hash1", "Admin"),
        )
        db.commit()

        # Duplicate username
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
                ("admin1", "scrypt:hash2", "Staff"),
            )

        # Invalid Role
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
                ("user2", "scrypt:hash3", "SuperAdmin"),
            )


def test_database_persistence(app):
    """Verify that records persist across distinct database connections to the file."""
    db_path = app.config["DATABASE"]
    
    # Insert record using first connection
    conn1 = sqlite3.connect(db_path)
    conn1.execute(
        "INSERT INTO Patient (P_Name, P_Age, P_Gender, Blood_Group) VALUES ('Persistent Patient', 50, 'Female', 'AB+')",
    )
    conn1.commit()
    conn1.close()

    # Reopen brand new connection to the file
    conn2 = sqlite3.connect(db_path)
    row = conn2.execute("SELECT P_Name, P_Age FROM Patient WHERE P_Name = 'Persistent Patient'").fetchone()
    conn2.close()

    assert row is not None
    assert row[0] == "Persistent Patient"
    assert row[1] == 50


def test_load_dataset_cli_and_seeder(runner, app):
    """Verify that flask load-dataset CLI command imports dataset CSVs and populates tables."""
    result = runner.invoke(args=["load-dataset"])
    assert "Dataset loaded successfully:" in result.output
    assert "50 patients" in result.output
    assert "10 doctors" in result.output
    assert "200 appointments" in result.output
    assert "200 bills" in result.output

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM Patient").fetchone()[0] == 50
        assert db.execute("SELECT COUNT(*) FROM Doctor").fetchone()[0] == 10
        assert db.execute("SELECT COUNT(*) FROM Appointment").fetchone()[0] == 200
        assert db.execute("SELECT COUNT(*) FROM Bill").fetchone()[0] == 200
