from flask import Blueprint, request, jsonify
from datetime import date as date_class
from db import get_db
from booking_lifecycle import expire_pending_requests, has_reservation
from site_settings import get_site_settings, slots_by_key

availability_bp = Blueprint("availability", __name__)

@availability_bp.route("/check-availability", methods=["POST"])
def check_availability():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    slot = data.get("slot", "").lower().strip()
    date_str = data.get("date", "").strip()

    slot_settings = slots_by_key(get_site_settings())
    if slot not in slot_settings:
        return jsonify({"error": "Invalid slot. Choose morning, afternoon, evening, or full_day."}), 400

    if not date_str:
        return jsonify({"error": "Date is required."}), 400

    try:
        booking_date = date_class.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if booking_date < date_class.today():
        return jsonify({"error": "Bookings cannot be made for past dates."}), 400

    try:
        db = get_db()
        expire_pending_requests(db)
        bookings = db["bookings"]
        reservation_conflict = has_reservation(db, date_str, slot)
        if date_str in get_site_settings().get("blackout_dates", []):
            return jsonify({"available": False, "message": "This date is unavailable."})

        # A slot is unavailable if:
        # 1. An existing booking has the same slot on the same date, OR
        # 2. An existing booking is full_day on the same date (blocks all), OR
        # 3. The requested slot is full_day and any booking exists on that date
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

        if conflict or reservation_conflict:
            return jsonify({"available": False, "message": "This slot is already booked."})

        return jsonify({"available": True, "price": slot_settings[slot]["price"]})

    except Exception as e:
        return jsonify({"error": "Database error. Please try again later."}), 500
