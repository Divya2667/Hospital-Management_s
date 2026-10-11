-- Hospital Management System SQLite Schema
-- Entities: User, Patient, Doctor, Appointment, Bill
-- Foreign Keys & Constraints Enforced

-- 1. User Entity (Authentication & Role Management)
CREATE TABLE IF NOT EXISTS User (
    User_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Username TEXT UNIQUE NOT NULL,
    Password_Hash TEXT NOT NULL,
    Role TEXT NOT NULL DEFAULT 'Admin' CHECK(Role IN ('Admin', 'Doctor', 'Staff')),
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Patient Entity
CREATE TABLE IF NOT EXISTS Patient (
    Patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    P_Name TEXT NOT NULL,
    P_Age INTEGER NOT NULL CHECK(P_Age >= 0 AND P_Age <= 120),
    P_Gender TEXT NOT NULL CHECK(P_Gender IN ('Male', 'Female', 'Other')),
    Blood_Group TEXT NOT NULL CHECK(Blood_Group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Doctor Entity
CREATE TABLE IF NOT EXISTS Doctor (
    Doctor_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    D_Name TEXT NOT NULL,
    D_Qualification TEXT NOT NULL,
    Experience INTEGER NOT NULL CHECK(Experience >= 0),
    D_Phone TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Appointment Entity (Patient 1:M Appointment, Doctor 1:M Appointment)
CREATE TABLE IF NOT EXISTS Appointment (
    Appointment_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Patient_id INTEGER NOT NULL,
    Doctor_ID INTEGER NOT NULL,
    A_Date TEXT NOT NULL,
    A_Time TEXT NOT NULL,
    Reason TEXT NOT NULL,
    Duration_Min INTEGER NOT NULL DEFAULT 30 CHECK(Duration_Min > 0),
    Status TEXT NOT NULL DEFAULT 'Scheduled' CHECK(Status IN ('Scheduled', 'Completed', 'Cancelled')),
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Patient_id) REFERENCES Patient(Patient_id) ON DELETE RESTRICT,
    FOREIGN KEY (Doctor_ID) REFERENCES Doctor(Doctor_ID) ON DELETE RESTRICT
);

-- 5. Bill Entity (Patient 1:M Bill)
CREATE TABLE IF NOT EXISTS Bill (
    Bill_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Patient_id INTEGER NOT NULL,
    B_Date TEXT NOT NULL,
    B_Amount REAL NOT NULL CHECK(B_Amount > 0),
    Pay_Mode TEXT NOT NULL CHECK(Pay_Mode IN ('Cash', 'Card', 'UPI', 'Insurance', 'Net Banking')),
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Patient_id) REFERENCES Patient(Patient_id) ON DELETE RESTRICT
);

-- 6. Treatment Entity (Appointment 1:M Treatment)
CREATE TABLE IF NOT EXISTS Treatment (
    Treatment_ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Appointment_ID INTEGER NOT NULL,
    Treatment_Type TEXT NOT NULL,
    Description TEXT,
    Cost REAL NOT NULL CHECK(Cost >= 0),
    Treatment_Date TEXT NOT NULL,
    Created_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (Appointment_ID) REFERENCES Appointment(Appointment_ID) ON DELETE RESTRICT
);

-- Indexes for performance and quick query lookup
CREATE INDEX IF NOT EXISTS idx_appointment_doctor_date ON Appointment(Doctor_ID, A_Date, A_Time);
CREATE INDEX IF NOT EXISTS idx_appointment_patient ON Appointment(Patient_id);
CREATE INDEX IF NOT EXISTS idx_appointment_status ON Appointment(Status);
CREATE INDEX IF NOT EXISTS idx_bill_patient ON Bill(Patient_id);
CREATE INDEX IF NOT EXISTS idx_bill_date ON Bill(B_Date);
CREATE INDEX IF NOT EXISTS idx_patient_active ON Patient(is_active);
CREATE INDEX IF NOT EXISTS idx_doctor_active ON Doctor(is_active);
CREATE INDEX IF NOT EXISTS idx_treatment_appointment ON Treatment(Appointment_ID);
