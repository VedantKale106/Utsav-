import os
from flask import Blueprint, request, jsonify
from datetime import date as date_class, datetime, timezone
from db import get_db

order_bp = Blueprint("order", __name__)

SLOT_PRICES = {
    "morning": 25000,
    "afternoon": 20000,
    "evening": 35000,
    "full_day": 70000,
}

VALID_SLOTS = set(SLOT_PRICES.keys())

@order_bp.route("/create-order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    date_str = data.get("date", "").strip()
    slot = data.get("slot", "").lower().strip()
    event_type = data.get("event_type", "").strip()

    # --- Validate required fields ---
    if not all([name, phone, date_str, slot, event_type]):
        return jsonify({"error": "All fields (name, phone, date, slot, event_type) are required."}), 400

    if len(phone) != 10 or not phone.isdigit():
        return jsonify({"error": "Phone number must be exactly 10 digits."}), 400

    if slot not in VALID_SLOTS:
        return jsonify({"error": "Invalid slot selected."}), 400

    try:
        booking_date = date_class.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    if booking_date < date_class.today():
        return jsonify({"error": "Cannot book for past dates."}), 400

    # --- Re-check availability (atomic guard before creating request) ---
    try:
        db = get_db()
        bookings = db["bookings"]

        if slot == "full_day":
            conflict = bookings.find_one({"date": date_str})
        else:
            conflict = bookings.find_one({
                "date": date_str,
                "$or": [
                    {"slot": slot},
                    {"slot": "full_day"},
                ]
            })

        if conflict:
            return jsonify({"error": "This slot was just booked by someone else. Please choose a different slot or date."}), 409

    except Exception:
        return jsonify({"error": "Database error. Please try again."}), 500

    # --- Create Booking Request ---
    try:
        booking_requests = db["booking_requests"]
        
        request_doc = {
            "name": name,
            "phone": phone,
            "date": date_str,
            "slot": slot,
            "event_type": event_type,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        booking_requests.insert_one(request_doc)
        
        # WhatsApp redirect URL logic here or return success
        slot_display = {
            "morning": "Morning (7 AM - 12 PM)",
            "afternoon": "Afternoon (12 PM - 5 PM)",
            "evening": "Evening (5 PM - 11 PM)",
            "full_day": "Full Day (7 AM - 11 PM)",
        }
        whatsapp_message = (
            f"Hello Utsav Banquet Hall! I have sent a booking request.%0A"
            f"Name: {name}%0A"
            f"Phone: {phone}%0A"
            f"Date: {date_str}%0A"
            f"Slot: {slot_display.get(slot, slot)}%0A"
            f"Event: {event_type}%0A"
            f"Please confirm my booking."
        )
        whatsapp_number = os.getenv("WHATSAPP_NUMBER", "919999999999")
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={whatsapp_message}"
        
        return jsonify({"success": True, "whatsapp_url": whatsapp_url})
    except Exception as e:
        return jsonify({"error": "Failed to create request. Please try again."}), 500

    return jsonify({
        "order_id": order["id"],
        "amount": amount_in_paise,
        "currency": "INR",
        "key_id": os.getenv("RAZORPAY_KEY_ID"),
        "advance_amount": advance_amount,
        "total_price": total_price,
        "booking_details": {
            "name": name,
            "phone": phone,
            "date": date_str,
            "slot": slot,
            "event_type": event_type,
        }
    })
