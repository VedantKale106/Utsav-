import os
from datetime import date as date_class, datetime, timezone
from urllib.parse import urlencode
from hmac import compare_digest
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
from db import get_db
from bson.objectid import ObjectId
from bson.errors import InvalidId
from werkzeug.security import check_password_hash, generate_password_hash
from booking_lifecycle import expire_pending_requests, has_reservation, release_slot, reservation_owned, reserve_slot, utc_now
from site_settings import get_site_settings, save_site_settings

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
LOGIN_FAILURES = {}


def get_object_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def audit(db, action, booking_id=None, details=None):
    db["audit_logs"].insert_one({
        "action": action,
        "admin": session.get("admin_username", "unknown"),
        "booking_id": str(booking_id) if booking_id else None,
        "details": details or {},
        "created_at": utc_now(),
    })


def customer_whatsapp_url(booking_request, status_message="declined", reason=""):
    customer_phone = "".join(character for character in booking_request.get("phone", "") if character.isdigit())
    if len(customer_phone) == 10:
        customer_phone = "91" + customer_phone
    if len(customer_phone) < 10:
        return ""

    site = get_site_settings()
    admin_phone = site.get("phone", "")
    outcome = "has been declined" if status_message == "declined" else "has been cancelled"
    next_step = (
        "Please contact us if you would like to choose another date or slot."
        if status_message == "declined"
        else "Please contact us if you have questions about this cancellation."
    )
    message = "\n".join([
        f"Hello {booking_request.get('name', '')},",
        f"This is {site.get('business_name', 'Utsav Banquet Hall')} ({admin_phone}).",
        f"Your booking for {booking_request.get('date', '')} ({booking_request.get('slot', '').replace('_', ' ')}) {outcome}.",
        f"Reason: {reason}" if reason else "",
        next_step,
    ])
    return f"https://wa.me/{customer_phone}?{urlencode({'text': message})}"


def admin_password_is_valid(password):
    credentials = get_db()["admin_credentials"].find_one({"_id": "main"})
    if credentials and credentials.get("password_hash"):
        return check_password_hash(credentials["password_hash"], password or "")
    stored_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    if stored_hash:
        return check_password_hash(stored_hash, password or "")
    return bool(ADMIN_PASSWORD) and compare_digest(password or "", ADMIN_PASSWORD)

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        client_ip = request.remote_addr or "unknown"
        now = datetime.now(timezone.utc).timestamp()
        failures = [stamp for stamp in LOGIN_FAILURES.get(client_ip, []) if now - stamp < 900]
        if len(failures) >= 5:
            return render_template("admin_login.html", error="Too many attempts. Try again in 15 minutes."), 429
        username = request.form.get("username")
        password = request.form.get("password")
        if (ADMIN_USERNAME and (ADMIN_PASSWORD or os.getenv("ADMIN_PASSWORD_HASH")) and
                compare_digest(username or "", ADMIN_USERNAME) and admin_password_is_valid(password)):
            LOGIN_FAILURES.pop(client_ip, None)
            session.clear()
            session["csrf_token"] = __import__("secrets").token_urlsafe(32)
            session["admin_logged_in"] = True
            session["admin_username"] = username
            session.permanent = True
            return redirect(url_for("admin.dashboard"))
        failures.append(now)
        LOGIN_FAILURES[client_ip] = failures
        return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")

@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not admin_password_is_valid(current_password):
            return render_template("admin_password.html", error="Current password is incorrect.")
        if len(new_password) < 12 or new_password != confirm_password:
            return render_template("admin_password.html", error="New passwords must match and be at least 12 characters.")
        db = get_db()
        db["admin_credentials"].replace_one(
            {"_id": "main"},
            {"_id": "main", "password_hash": generate_password_hash(new_password), "updated_at": utc_now()},
            upsert=True,
        )
        audit(db, "admin_password_changed", details={})
        return render_template("admin_password.html", saved=True)
    return render_template("admin_password.html")

@admin_bp.route("/")
def dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    expire_pending_requests(db)
    requests = list(db["booking_requests"].find({"status": "pending"}).sort("date", 1))
    bookings = list(db["bookings"].find().sort("date", -1))
    return render_template("admin_dashboard.html", requests=requests, bookings=bookings)

@admin_bp.route("/accept/<req_id>", methods=["POST"])
def accept_request(req_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    expire_pending_requests(db)
    request_id = get_object_id(req_id)
    if request_id is None:
        return redirect(url_for("admin.dashboard", error="Invalid request ID."))
    req = db["booking_requests"].find_one({"_id": request_id, "status": "pending"})
    if not req:
        return jsonify({"error": "Request not found"}), 404
        
    date_str = req["date"]
    slot = req["slot"]
    
    # check if already booked in bookings collection
    if slot == "full_day":
        conflict = db["bookings"].find_one({"date": date_str})
    else:
        conflict = db["bookings"].find_one({
            "date": date_str,
            "$or": [
                {"slot": slot},
                {"slot": "full_day"}
            ]
        })
        
    if conflict:
        return redirect(url_for("admin.dashboard", error="This slot is already booked."))

    if req.get("expires_at") and req["expires_at"] <= utc_now():
        db["booking_requests"].update_one({"_id": request_id}, {"$set": {"status": "expired", "status_updated_at": utc_now()}})
        release_slot(db, date_str, slot, str(request_id))
        return redirect(url_for("admin.dashboard", error="This request has expired."))

    if has_reservation(db, date_str, slot) and not reservation_owned(db, date_str, slot, str(request_id)):
        return redirect(url_for("admin.dashboard", error="This slot is no longer available."))
    if not has_reservation(db, date_str, slot) and not reserve_slot(db, date_str, slot, str(request_id)):
        return redirect(url_for("admin.dashboard", error="This slot is no longer available."))

    claimed = db["booking_requests"].update_one(
        {"_id": request_id, "status": "pending"},
        {"$set": {"status": "accepted", "status_updated_at": utc_now()}},
    )
    if claimed.modified_count != 1:
        return redirect(url_for("admin.dashboard", error="This request was already processed."))

    # Insert into bookings after claiming the request so two admins cannot approve it twice.
    booking_doc = {
        "name": req["name"],
        "phone": req["phone"],
        "date": req["date"],
        "slot": req["slot"],
        "event_type": req["event_type"],
        "status": "confirmed",
        "created_at": req["created_at"],
        "request_id": str(req["_id"]),
    }
    
    try:
        db["bookings"].insert_one(booking_doc)
        audit(db, "booking_approved", request_id, {"date": date_str, "slot": slot})
    except Exception:
        db["booking_requests"].update_one({"_id": request_id}, {"$set": {"status": "pending"}})
        return redirect(url_for("admin.dashboard", error="Could not approve this request."))
        
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/reject/<req_id>", methods=["POST"])
def reject_request(req_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
        
    db = get_db()
    request_id = get_object_id(req_id)
    if request_id is None:
        return redirect(url_for("admin.dashboard", error="Invalid request ID."))
    booking_request = db["booking_requests"].find_one({"_id": request_id, "status": "pending"})
    if not booking_request:
        return redirect(url_for("admin.dashboard", error="Request not found."))
    reason = request.form.get("reason", "").strip()[:300]
    if not reason:
        return redirect(url_for("admin.dashboard", error="A decline reason is required."))
    db["booking_requests"].update_one(
        {"_id": request_id},
        {"$set": {"status": "rejected", "reason": reason, "status_updated_at": utc_now()}}
    )
    release_slot(db, booking_request.get("date", ""), booking_request.get("slot", ""), str(request_id))
    audit(db, "request_declined", request_id, {"reason": reason})
    notify_url = customer_whatsapp_url(booking_request, reason=reason)
    if notify_url:
        return redirect(url_for("admin.dashboard", msg="Request declined.", notify_url=notify_url))
    return redirect(url_for("admin.dashboard", error="Request declined, but the customer phone number is invalid."))

@admin_bp.route("/delete-booking/<booking_id>", methods=["POST"])
def delete_booking(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
        
    db = get_db()
    booking_object_id = get_object_id(booking_id)
    if booking_object_id is None:
        return redirect(url_for("admin.dashboard", error="Invalid booking ID."))
    booking = db["bookings"].find_one({"_id": booking_object_id})
    if not booking:
        return redirect(url_for("admin.dashboard", error="Booking not found"))

    request_id = booking.get("request_id")
    reason = request.form.get("reason", "").strip()[:300]
    if not reason:
        return redirect(url_for("admin.dashboard", error="A cancellation reason is required."))
    if request_id:
        try:
            db["booking_requests"].update_one(
                {"_id": get_object_id(request_id)},
                {"$set": {"status": "cancelled", "reason": reason, "status_updated_at": utc_now()}},
            )
        except Exception:
            pass
    else:
        # Backfill a rejected entry for legacy confirmed bookings without request_id.
        db["booking_requests"].insert_one(
            {
                "name": booking.get("name", ""),
                "phone": booking.get("phone", ""),
                "date": booking.get("date", ""),
                "slot": booking.get("slot", ""),
                "event_type": booking.get("event_type", ""),
                "status": "cancelled",
                "reason": reason,
                "created_at": booking.get("created_at"),
            }
        )

    release_slot(db, booking.get("date", ""), booking.get("slot", ""), request_id)
    audit(db, "booking_cancelled", booking_object_id, {"reason": reason})
    notify_url = customer_whatsapp_url(booking, "cancelled", reason)
    db["bookings"].delete_one({"_id": booking_object_id})
    if notify_url:
        return redirect(url_for("admin.dashboard", msg="Booking deleted.", notify_url=notify_url))
    return redirect(url_for("admin.dashboard", error="Booking deleted, but the customer phone number is invalid."))


@admin_bp.route("/complete-booking/<booking_id>", methods=["POST"])
def complete_booking(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    booking_object_id = get_object_id(booking_id)
    if booking_object_id is None:
        return redirect(url_for("admin.dashboard", error="Invalid booking ID."))
    db = get_db()
    result = db["bookings"].update_one(
        {"_id": booking_object_id, "status": "confirmed"},
        {"$set": {"status": "completed", "completed_at": utc_now()}},
    )
    if result.modified_count != 1:
        return redirect(url_for("admin.dashboard", error="Booking is already completed or unavailable."))
    audit(db, "booking_completed", booking_object_id, {})
    request_id = db["bookings"].find_one({"_id": booking_object_id}).get("request_id")
    if request_id:
        db["booking_requests"].update_one({"_id": get_object_id(request_id)}, {"$set": {"status": "completed"}})
    return redirect(url_for("admin.dashboard", msg="Booking marked as completed."))

@admin_bp.route("/rejected")
def rejected():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    requests = list(db["booking_requests"].find({"status": {"$in": ["rejected", "cancelled", "expired"]}}).sort("date", -1))
    return render_template("admin_rejected.html", requests=requests)


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    current = get_site_settings()
    if request.method == "POST":
        updated = {
            "business_name": request.form.get("business_name", "").strip(),
            "address": request.form.get("address", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "map_embed_url": request.form.get("map_embed_url", "").strip(),
            "pending_request_expiry_hours": 48,
            "blackout_dates": [],
            "slots": [],
            "highlights": [],
            "stats": [],
        }

        if not all(updated[key] for key in ("business_name", "address", "phone", "email")):
            return render_template("admin_settings.html", site=current, error="Business details cannot be empty.")
        if not updated["map_embed_url"].startswith("https://www.google.com/maps/embed"):
            return render_template("admin_settings.html", site=current, error="Use a valid Google Maps embed URL.")
        try:
            updated["pending_request_expiry_hours"] = int(request.form.get("pending_request_expiry_hours", "48"))
        except ValueError:
            updated["pending_request_expiry_hours"] = 0
        if not 1 <= updated["pending_request_expiry_hours"] <= 168:
            return render_template("admin_settings.html", site=current, error="Request expiry must be between 1 and 168 hours.")
        for raw_date in request.form.get("blackout_dates", "").splitlines():
            raw_date = raw_date.strip()
            if not raw_date:
                continue
            try:
                blocked_date = date_class.fromisoformat(raw_date)
            except ValueError:
                return render_template("admin_settings.html", site=current, error=f"Invalid blackout date: {raw_date}")
            if blocked_date >= date_class.today() and raw_date not in updated["blackout_dates"]:
                updated["blackout_dates"].append(raw_date)

        for slot in current["slots"]:
            key = slot["key"]
            try:
                price = int(request.form.get(f"slot_price_{key}", "0"))
            except ValueError:
                price = 0
            if not 0 < price <= 10000000:
                return render_template("admin_settings.html", site=current, error="Slot prices must be between Rs. 1 and Rs. 1 crore.")
            updated["slots"].append({
                "key": key,
                "label": request.form.get(f"slot_label_{key}", "").strip()[:40],
                "time": request.form.get(f"slot_time_{key}", "").strip()[:60],
                "price": price,
                "description": request.form.get(f"slot_description_{key}", "").strip()[:240],
                "featured": request.form.get(f"slot_featured_{key}") == "on",
                "active": request.form.get(f"slot_active_{key}") == "on",
            })

        for index, highlight in enumerate(current["highlights"]):
            updated["highlights"].append({
                "title": request.form.get(f"highlight_title_{index}", "").strip()[:60],
                "description": request.form.get(f"highlight_description_{index}", "").strip()[:160],
            })

        for index, stat in enumerate(current["stats"]):
            updated["stats"].append({
                "value": request.form.get(f"stat_value_{index}", "").strip()[:30],
                "label": request.form.get(f"stat_label_{index}", "").strip()[:60],
            })

        if any(not item["label"] for item in updated["slots"]):
            return render_template("admin_settings.html", site=current, error="Every slot needs a label.")
        if not any(item["active"] for item in updated["slots"]):
            return render_template("admin_settings.html", site=current, error="At least one booking slot must remain active.")

        try:
            save_site_settings(updated)
        except Exception:
            return render_template("admin_settings.html", site=current, error="Could not save settings. Please try again.")
        audit(get_db(), "site_settings_updated", details={"blackout_dates": updated["blackout_dates"]})
        return redirect(url_for("admin.settings", saved="1"))

    return render_template("admin_settings.html", site=current)
