import os
from urllib.parse import urlencode
from flask import Blueprint, request, jsonify
from datetime import date as date_class, datetime, timezone
from bson import ObjectId
from db import get_db
from booking_lifecycle import expire_pending_requests, normalize_phone, reserve_slot, request_expiry
from site_settings import get_site_settings, slots_by_key

order_bp = Blueprint("order", __name__)

@order_bp.route("/create-booking-request", methods=["POST"])
def create_booking_request():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    date_str = data.get("date", "").strip()
    slot = data.get("slot", "").lower().strip()
    event_type = data.get("event_type", "").strip()
    consent = data.get("consent") is True

    # --- Validate required fields ---
    if not all([name, phone, date_str, slot, event_type]) or not consent:
        return jsonify({"error": "All fields (name, phone, date, slot, event_type) are required."}), 400

    if len(name) > 100 or len(event_type) > 80:
        return jsonify({"error": "Name or event type is too long."}), 400

    phone = normalize_phone(phone)
    if len(phone) != 10 or not phone.isdigit() or phone[0] not in "6789":
        return jsonify({"error": "Enter a valid Indian mobile number."}), 400

    slot_settings = slots_by_key(get_site_settings())
    if slot not in slot_settings:
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
        expire_pending_requests(db)
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

        settings = get_site_settings()
        if date_str in settings.get("blackout_dates", []):
            return jsonify({"error": "This date is unavailable. Please choose another date."}), 409

        duplicate = db["booking_requests"].find_one({
            "phone_normalized": phone,
            "date": date_str,
            "slot": slot,
            "status": {"$in": ["pending", "accepted"]},
        })
        if duplicate:
            return jsonify({"error": "You already have an active request for this date and slot."}), 409

    except Exception:
        return jsonify({"error": "Database error. Please try again."}), 500

    # --- Create Booking Request ---
    try:
        booking_requests = db["booking_requests"]
        
        request_id = ObjectId()
        request_doc = {
            "_id": request_id,
            "name": name,
            "phone": phone,
            "phone_normalized": phone,
            "date": date_str,
            "slot": slot,
            "event_type": event_type,
            "status": "pending",
            "expires_at": request_expiry(settings.get("pending_request_expiry_hours", 48)),
            "status_updated_at": datetime.now(timezone.utc),
            "consent_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if not reserve_slot(db, date_str, slot, str(request_id)):
            return jsonify({"error": "This slot was just requested by someone else. Please choose a different slot or date."}), 409
        try:
            booking_requests.insert_one(request_doc)
        except Exception:
            from booking_lifecycle import release_slot
            release_slot(db, date_str, slot, str(request_id))
            raise
        
        # WhatsApp redirect URL logic here or return success
        selected_slot = slot_settings[slot]
        slot_display = f"{selected_slot['label']} ({selected_slot['time']})"
        whatsapp_message = "\n".join([
            "Hello Utsav Banquet Hall! I have sent a booking request.",
            f"Name: {name}",
            f"Phone: {phone}",
            f"Date: {date_str}",
            f"Slot: {slot_display}",
            f"Event: {event_type}",
            "Please confirm my booking.",
        ])
        whatsapp_number = os.getenv("WHATSAPP_NUMBER", "")
        whatsapp_url = ""
        if whatsapp_number.isdigit():
            whatsapp_url = f"https://wa.me/{whatsapp_number}?{urlencode({'text': whatsapp_message})}"
        
        return jsonify({"success": True, "whatsapp_url": whatsapp_url})
    except Exception:
        return jsonify({"error": "Failed to create request. Please try again."}), 500

