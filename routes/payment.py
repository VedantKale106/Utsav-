import os
import hmac
import hashlib
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from pymongo.errors import DuplicateKeyError
from db import get_db

payment_bp = Blueprint("payment", __name__)

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "919999999999")


@payment_bp.route("/verify-payment", methods=["POST"])
def verify_payment():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    razorpay_order_id = data.get("razorpay_order_id", "")
    razorpay_payment_id = data.get("razorpay_payment_id", "")
    razorpay_signature = data.get("razorpay_signature", "")
    booking_details = data.get("booking_details", {})

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return jsonify({"error": "Missing payment verification fields."}), 400

    # --- Verify HMAC signature ---
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    body = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        key_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, razorpay_signature):
        return jsonify({"error": "Payment verification failed. Invalid signature."}), 400

    # --- Store booking in MongoDB ---
    name = booking_details.get("name", "")
    phone = booking_details.get("phone", "")
    date_str = booking_details.get("date", "")
    slot = booking_details.get("slot", "")
    event_type = booking_details.get("event_type", "")

    SLOT_PRICES = {
        "morning": 25000,
        "afternoon": 20000,
        "evening": 35000,
        "full_day": 70000,
    }

    total_price = SLOT_PRICES.get(slot, 0)
    advance_paid = int(total_price * 0.30)
    balance_due = total_price - advance_paid

    try:
        db = get_db()
        bookings = db["bookings"]

        booking_doc = {
            "name": name,
            "phone": phone,
            "date": date_str,
            "slot": slot,
            "event_type": event_type,
            "total_price": total_price,
            "advance_paid": advance_paid,
            "balance_due": balance_due,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "status": "confirmed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        bookings.insert_one(booking_doc)

    except DuplicateKeyError:
        # The unique index on (date, slot) caught a race condition
        return jsonify({"error": "This slot was booked concurrently. Please choose another slot."}), 409
    except Exception:
        return jsonify({"error": "Failed to save booking. Please contact us."}), 500

    # --- Build WhatsApp redirect URL ---
    slot_display = {
        "morning": "Morning (7 AM - 12 PM)",
        "afternoon": "Afternoon (12 PM - 5 PM)",
        "evening": "Evening (5 PM - 11 PM)",
        "full_day": "Full Day (7 AM - 11 PM)",
    }
    whatsapp_message = (
        f"Hello Utsav Banquet Hall! My booking is confirmed.%0A"
        f"Name: {name}%0A"
        f"Phone: {phone}%0A"
        f"Date: {date_str}%0A"
        f"Slot: {slot_display.get(slot, slot)}%0A"
        f"Event: {event_type}%0A"
        f"Payment ID: {razorpay_payment_id}%0A"
        f"Advance Paid: Rs. {advance_paid:,}%0A"
        f"Balance Due: Rs. {balance_due:,}"
    )
    whatsapp_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={whatsapp_message}"

    return jsonify({
        "success": True,
        "message": "Booking confirmed successfully.",
        "whatsapp_url": whatsapp_url,
        "payment_id": razorpay_payment_id,
        "advance_paid": advance_paid,
        "balance_due": balance_due,
    })
