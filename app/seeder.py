import os
import csv
import logging
from pathlib import Path
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

BLOOD_GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
PAYMENT_MODE_MAP = {
    "Credit Card": "Card",
    "Debit Card": "Card",
    "Card": "Card",
    "Cash": "Cash",
    "UPI": "UPI",
    "Insurance": "Insurance",
    "Net Banking": "Net Banking",
}


def find_dataset_dir(custom_path=None):
    """Locate the dataset directory containing CSV files."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))

    # Project root dataset
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    candidates.append(project_root / "dataset")
    candidates.append(Path.cwd() / "dataset")

    for c in candidates:
        if c.exists() and (c / "patients.csv").exists():
            return c
    return None


def import_csv_dataset(db, dataset_dir=None):
    """Import records from dataset CSV files into the SQLite database.
    
    Returns a dict summary of imported row counts.
    """
    data_dir = find_dataset_dir(dataset_dir)
    if not data_dir:
        raise FileNotFoundError(f"Could not locate dataset folder. Searched candidates from {Path.cwd()}")

    stats = {
        "patients": 0,
        "doctors": 0,
        "appointments": 0,
        "treatments": 0,
        "bills": 0,
        "admin_created": False,
    }

    # Ensure foreign keys are enabled
    db.execute("PRAGMA foreign_keys = ON;")

    # 1. Patients
    patients_file = data_dir / "patients.csv"
    if patients_file.exists():
        with open(patients_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_raw_id = row.get("patient_id", "").strip()
                if not p_raw_id:
                    continue
                patient_id = int(p_raw_id.replace("P", "").lstrip("0") or "0")
                first = row.get("first_name", "").strip()
                last = row.get("last_name", "").strip()
                name = f"{first} {last}".strip() or f"Patient {patient_id}"

                dob = row.get("date_of_birth", "").strip()
                birth_year = int(dob[:4]) if dob and len(dob) >= 4 and dob[:4].isdigit() else 1985
                # Hospital local reference year 2026
                age = max(0, min(120, 2026 - birth_year))

                raw_gender = row.get("gender", "").strip().upper()
                gender = "Male" if raw_gender == "M" else ("Female" if raw_gender == "F" else "Other")

                blood_group = BLOOD_GROUPS[(patient_id - 1) % len(BLOOD_GROUPS)]

                db.execute(
                    """
                    INSERT INTO Patient (Patient_id, P_Name, P_Age, P_Gender, Blood_Group, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(Patient_id) DO UPDATE SET
                        P_Name = excluded.P_Name,
                        P_Age = excluded.P_Age,
                        P_Gender = excluded.P_Gender,
                        Blood_Group = excluded.Blood_Group,
                        is_active = 1
                    """,
                    (patient_id, name, age, gender, blood_group),
                )
                stats["patients"] += 1

    # 2. Doctors
    doctors_file = data_dir / "doctors.csv"
    if doctors_file.exists():
        with open(doctors_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_raw_id = row.get("doctor_id", "").strip()
                if not d_raw_id:
                    continue
                doctor_id = int(d_raw_id.replace("D", "").lstrip("0") or "0")
                first = row.get("first_name", "").strip()
                last = row.get("last_name", "").strip()
                name = f"Dr. {first} {last}".strip()

                spec = row.get("specialization", "General Medicine").strip()
                qual = f"MD {spec}"
                exp = int(row.get("years_experience", 5))
                phone = row.get("phone_number", "555-0100").strip()

                db.execute(
                    """
                    INSERT INTO Doctor (Doctor_ID, D_Name, D_Qualification, Experience, D_Phone, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(Doctor_ID) DO UPDATE SET
                        D_Name = excluded.D_Name,
                        D_Qualification = excluded.D_Qualification,
                        Experience = excluded.Experience,
                        D_Phone = excluded.D_Phone,
                        is_active = 1
                    """,
                    (doctor_id, name, qual, exp, phone),
                )
                stats["doctors"] += 1

    # 3. Appointments
    appts_file = data_dir / "appointments.csv"
    if appts_file.exists():
        with open(appts_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a_raw_id = row.get("appointment_id", "").strip()
                if not a_raw_id:
                    continue
                appt_id = int(a_raw_id.replace("A", "").lstrip("0") or "0")
                p_id = int(row.get("patient_id", "P1").replace("P", "").lstrip("0") or "1")
                d_id = int(row.get("doctor_id", "D1").replace("D", "").lstrip("0") or "1")
                a_date = row.get("appointment_date", "").strip()
                raw_time = row.get("appointment_time", "09:00").strip()
                a_time = raw_time[:5] if len(raw_time) >= 5 else "09:00"
                reason = row.get("reason_for_visit", "Consultation").strip()

                raw_status = row.get("status", "Scheduled").strip()
                if raw_status.lower() in ("no-show", "noshow"):
                    status = "Cancelled"
                elif raw_status in ("Scheduled", "Completed", "Cancelled"):
                    status = raw_status
                else:
                    status = "Scheduled"

                db.execute(
                    """
                    INSERT INTO Appointment (Appointment_ID, Patient_id, Doctor_ID, A_Date, A_Time, Reason, Duration_Min, Status)
                    VALUES (?, ?, ?, ?, ?, ?, 30, ?)
                    ON CONFLICT(Appointment_ID) DO UPDATE SET
                        Patient_id = excluded.Patient_id,
                        Doctor_ID = excluded.Doctor_ID,
                        A_Date = excluded.A_Date,
                        A_Time = excluded.A_Time,
                        Reason = excluded.Reason,
                        Duration_Min = 30,
                        Status = excluded.Status
                    """,
                    (appt_id, p_id, d_id, a_date, a_time, reason, status),
                )
                stats["appointments"] += 1

    # 4. Treatments (if Treatment table is present)
    treatments_file = data_dir / "treatments.csv"
    has_treatment_table = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='Treatment'"
    ).fetchone() is not None

    if treatments_file.exists() and has_treatment_table:
        with open(treatments_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t_raw_id = row.get("treatment_id", "").strip()
                if not t_raw_id:
                    continue
                t_id = int(t_raw_id.replace("T", "").lstrip("0") or "0")
                a_id = int(row.get("appointment_id", "A1").replace("A", "").lstrip("0") or "1")
                t_type = row.get("treatment_type", "General").strip()
                desc = row.get("description", "").strip()
                cost = float(row.get("cost", 0.0))
                t_date = row.get("treatment_date", "").strip()

                db.execute(
                    """
                    INSERT INTO Treatment (Treatment_ID, Appointment_ID, Treatment_Type, Description, Cost, Treatment_Date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(Treatment_ID) DO UPDATE SET
                        Appointment_ID = excluded.Appointment_ID,
                        Treatment_Type = excluded.Treatment_Type,
                        Description = excluded.Description,
                        Cost = excluded.Cost,
                        Treatment_Date = excluded.Treatment_Date
                    """,
                    (t_id, a_id, t_type, desc, cost, t_date),
                )
                stats["treatments"] += 1

    # 5. Billing
    billing_file = data_dir / "billing.csv"
    if billing_file.exists():
        with open(billing_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                b_raw_id = row.get("bill_id", "").strip()
                if not b_raw_id:
                    continue
                bill_id = int(b_raw_id.replace("B", "").lstrip("0") or "0")
                p_id = int(row.get("patient_id", "P1").replace("P", "").lstrip("0") or "1")
                b_date = row.get("bill_date", "").strip()
                amount = float(row.get("amount", 100.0))
                raw_pay = row.get("payment_method", "Cash").strip()
                pay_mode = PAYMENT_MODE_MAP.get(raw_pay, "Cash")

                db.execute(
                    """
                    INSERT INTO Bill (Bill_ID, Patient_id, B_Date, B_Amount, Pay_Mode)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(Bill_ID) DO UPDATE SET
                        Patient_id = excluded.Patient_id,
                        B_Date = excluded.B_Date,
                        B_Amount = excluded.B_Amount,
                        Pay_Mode = excluded.Pay_Mode
                    """,
                    (bill_id, p_id, b_date, amount, pay_mode),
                )
                stats["bills"] += 1

    # 6. Ensure Default Administrator
    admin = db.execute("SELECT User_ID FROM User WHERE Username = 'admin'").fetchone()
    if not admin:
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, 'Admin')",
            ("admin", generate_password_hash("admin123")),
        )
        stats["admin_created"] = True

    db.commit()
    return stats
