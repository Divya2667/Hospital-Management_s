from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from app.auth import login_required
from app.db import get_db
from app.validators import ALLOWED_PAYMENT_MODES, validate_bill

bp = Blueprint("billing", __name__, url_prefix="/billing")


@bp.route("/")
@login_required
def index():
    """Listing view of all billing records and invoices with multi-criteria filters,
    search by patient or invoice number, and financial aggregates."""
    db = get_db()

    q = request.args.get("q", "").strip()
    pay_mode = request.args.get("pay_mode", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    base_query = """
        SELECT b.Bill_ID, b.Patient_id, b.B_Date, b.B_Amount, b.Pay_Mode, b.Created_At,
               p.P_Name as Patient_Name, p.P_Age as Patient_Age, p.P_Gender as Patient_Gender,
               p.Blood_Group as Patient_Blood_Group
        FROM Bill b
        JOIN Patient p ON b.Patient_id = p.Patient_id
    """
    conditions = []
    params = []

    if q:
        if q.isdigit():
            conditions.append("(b.Bill_ID = ? OR p.P_Name LIKE ?)")
            params.extend([int(q), f"%{q}%"])
        else:
            conditions.append("p.P_Name LIKE ?")
            params.append(f"%{q}%")

    if pay_mode and pay_mode in ALLOWED_PAYMENT_MODES:
        conditions.append("b.Pay_Mode = ?")
        params.append(pay_mode)

    if date_from:
        conditions.append("b.B_Date >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("b.B_Date <= ?")
        params.append(date_to)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"{base_query}{where_clause} ORDER BY b.B_Date DESC, b.Bill_ID DESC"
    bills = db.execute(query, params).fetchall()

    # Aggregate calculations for filtered results
    total_revenue = sum(b["B_Amount"] for b in bills)
    total_invoices = len(bills)
    avg_invoice = (total_revenue / total_invoices) if total_invoices > 0 else 0.0

    # Payment mode breakdown for filtered dataset
    mode_breakdown = {mode: {"count": 0, "amount": 0.0} for mode in ALLOWED_PAYMENT_MODES}
    for b in bills:
        m = b["Pay_Mode"]
        if m in mode_breakdown:
            mode_breakdown[m]["count"] += 1
            mode_breakdown[m]["amount"] += b["B_Amount"]

    # Lifetime overall totals for context
    lifetime = db.execute(
        "SELECT COUNT(*) as count, COALESCE(SUM(B_Amount), 0.0) as total FROM Bill"
    ).fetchone()

    return render_template(
        "billing/index.html",
        bills=bills,
        total_revenue=total_revenue,
        total_invoices=total_invoices,
        avg_invoice=avg_invoice,
        mode_breakdown=mode_breakdown,
        lifetime_count=lifetime["count"] if lifetime else 0,
        lifetime_revenue=lifetime["total"] if lifetime else 0.0,
        search_query=q,
        current_pay_mode=pay_mode,
        current_date_from=date_from,
        current_date_to=date_to,
        allowed_modes=ALLOWED_PAYMENT_MODES,
    )


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """Create a new hospital invoice / billing record."""
    db = get_db()
    today_str = date.today().isoformat()

    # Fetch active patients for billing assignment
    patients = db.execute(
        "SELECT Patient_id, P_Name, P_Age, P_Gender, Blood_Group FROM Patient WHERE is_active = 1 ORDER BY P_Name ASC"
    ).fetchall()

    if request.method == "POST":
        patient_id_raw = request.form.get("patient_id")
        b_date_raw = request.form.get("b_date")
        b_amount_raw = request.form.get("b_amount")
        pay_mode_raw = request.form.get("pay_mode")

        errors, cleaned = validate_bill(
            patient_id_raw=patient_id_raw,
            date_str=b_date_raw,
            amount_raw=b_amount_raw,
            pay_mode=pay_mode_raw,
            db=db,
        )

        if errors:
            for error in errors:
                flash(error, "danger")
            form_data = {
                "patient_id": patient_id_raw,
                "b_date": b_date_raw,
                "b_amount": b_amount_raw,
                "pay_mode": pay_mode_raw,
            }
            return render_template(
                "billing/create.html",
                patients=patients,
                form_data=form_data,
                allowed_modes=ALLOWED_PAYMENT_MODES,
                today_str=today_str,
            )

        cursor = db.execute(
            """
            INSERT INTO Bill (Patient_id, B_Date, B_Amount, Pay_Mode)
            VALUES (?, ?, ?, ?)
            """,
            (
                cleaned["Patient_id"],
                cleaned["B_Date"],
                cleaned["B_Amount"],
                cleaned["Pay_Mode"],
            ),
        )
        db.commit()
        new_bill_id = cursor.lastrowid

        flash(
            f"Invoice #{new_bill_id} generated successfully for ${cleaned['B_Amount']:.2f}.",
            "success",
        )
        return redirect(url_for("billing.detail", bill_id=new_bill_id))

    # Pre-selection support via query parameter
    preselect_patient_id = request.args.get("patient_id", type=int)
    form_data = {
        "patient_id": preselect_patient_id or "",
        "b_date": today_str,
        "b_amount": "",
        "pay_mode": "Cash",
    }

    return render_template(
        "billing/create.html",
        patients=patients,
        form_data=form_data,
        allowed_modes=ALLOWED_PAYMENT_MODES,
        today_str=today_str,
    )


@bp.route("/<int:bill_id>")
@login_required
def detail(bill_id):
    """Detailed view and printable invoice / receipt for a billing record."""
    db = get_db()
    bill = db.execute(
        """
        SELECT b.Bill_ID, b.Patient_id, b.B_Date, b.B_Amount, b.Pay_Mode, b.Created_At,
               p.P_Name as Patient_Name, p.P_Age as Patient_Age, p.P_Gender as Patient_Gender,
               p.Blood_Group as Patient_Blood_Group
        FROM Bill b
        JOIN Patient p ON b.Patient_id = p.Patient_id
        WHERE b.Bill_ID = ?
        """,
        (bill_id,),
    ).fetchone()

    if not bill:
        abort(404)

    # Optional clinical context: recent appointments for this patient
    appointments = db.execute(
        """
        SELECT a.Appointment_ID, a.A_Date, a.A_Time, a.Reason, a.Status,
               d.D_Name as Doctor_Name, d.D_Qualification
        FROM Appointment a
        JOIN Doctor d ON a.Doctor_ID = d.Doctor_ID
        WHERE a.Patient_id = ?
        ORDER BY a.A_Date DESC, a.A_Time DESC
        LIMIT 3
        """,
        (bill["Patient_id"],),
    ).fetchall()

    return render_template(
        "billing/detail.html",
        bill=bill,
        appointments=appointments,
    )


@bp.route("/<int:bill_id>/edit", methods=["GET", "POST"])
@login_required
def edit(bill_id):
    """Edit an existing billing record."""
    db = get_db()
    bill = db.execute(
        """
        SELECT b.Bill_ID, b.Patient_id, b.B_Date, b.B_Amount, b.Pay_Mode,
               p.P_Name as Patient_Name
        FROM Bill b
        JOIN Patient p ON b.Patient_id = p.Patient_id
        WHERE b.Bill_ID = ?
        """,
        (bill_id,),
    ).fetchone()

    if not bill:
        abort(404)

    # All active patients plus the currently selected patient if they are inactive
    patients = db.execute(
        """
        SELECT Patient_id, P_Name, P_Age, P_Gender, Blood_Group
        FROM Patient
        WHERE is_active = 1 OR Patient_id = ?
        ORDER BY P_Name ASC
        """,
        (bill["Patient_id"],),
    ).fetchall()

    if request.method == "POST":
        patient_id_raw = request.form.get("patient_id")
        b_date_raw = request.form.get("b_date")
        b_amount_raw = request.form.get("b_amount")
        pay_mode_raw = request.form.get("pay_mode")

        errors, cleaned = validate_bill(
            patient_id_raw=patient_id_raw,
            date_str=b_date_raw,
            amount_raw=b_amount_raw,
            pay_mode=pay_mode_raw,
            db=db,
        )

        if errors:
            for error in errors:
                flash(error, "danger")
            form_data = {
                "patient_id": patient_id_raw,
                "b_date": b_date_raw,
                "b_amount": b_amount_raw,
                "pay_mode": pay_mode_raw,
            }
            return render_template(
                "billing/edit.html",
                bill=bill,
                patients=patients,
                form_data=form_data,
                allowed_modes=ALLOWED_PAYMENT_MODES,
            )

        db.execute(
            """
            UPDATE Bill
            SET Patient_id = ?, B_Date = ?, B_Amount = ?, Pay_Mode = ?
            WHERE Bill_ID = ?
            """,
            (
                cleaned["Patient_id"],
                cleaned["B_Date"],
                cleaned["B_Amount"],
                cleaned["Pay_Mode"],
                bill_id,
            ),
        )
        db.commit()

        flash(f"Invoice #{bill_id} updated successfully.", "success")
        return redirect(url_for("billing.detail", bill_id=bill_id))

    form_data = {
        "patient_id": bill["Patient_id"],
        "b_date": bill["B_Date"],
        "b_amount": f"{bill['B_Amount']:.2f}",
        "pay_mode": bill["Pay_Mode"],
    }

    return render_template(
        "billing/edit.html",
        bill=bill,
        patients=patients,
        form_data=form_data,
        allowed_modes=ALLOWED_PAYMENT_MODES,
    )


@bp.route("/<int:bill_id>/delete", methods=["POST"])
@login_required
def delete(bill_id):
    """Delete a billing record."""
    db = get_db()
    bill = db.execute(
        "SELECT Bill_ID, B_Amount FROM Bill WHERE Bill_ID = ?", (bill_id,)
    ).fetchone()

    if not bill:
        abort(404)

    db.execute("DELETE FROM Bill WHERE Bill_ID = ?", (bill_id,))
    db.commit()

    flash(f"Invoice #{bill_id} (${bill['B_Amount']:.2f}) was permanently deleted.", "info")
    return redirect(url_for("billing.index"))
