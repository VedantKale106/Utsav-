import os
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
from db import get_db
from bson.objectid import ObjectId

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin.dashboard"))
        return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")

@admin_bp.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin.login"))

@admin_bp.route("/")
def dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    requests = list(db["booking_requests"].find({"status": "pending"}).sort("date", 1))
    bookings = list(db["bookings"].find().sort("date", -1))
    return render_template("admin_dashboard.html", requests=requests, bookings=bookings)

@admin_bp.route("/accept/<req_id>", methods=["POST"])
def accept_request(req_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    req = db["booking_requests"].find_one({"_id": ObjectId(req_id)})
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

    # Insert into bookings
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
        db["booking_requests"].update_one(
            {"_id": ObjectId(req_id)},
            {"$set": {"status": "accepted"}}
        )
    except Exception as e:
        pass
        
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/reject/<req_id>", methods=["POST"])
def reject_request(req_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
        
    db = get_db()
    db["booking_requests"].update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "rejected"}}
    )
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/delete-booking/<booking_id>", methods=["POST"])
def delete_booking(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
        
    db = get_db()
    booking = db["bookings"].find_one({"_id": ObjectId(booking_id)})
    if not booking:
        return redirect(url_for("admin.dashboard", error="Booking not found"))

    request_id = booking.get("request_id")
    if request_id:
        try:
            db["booking_requests"].update_one(
                {"_id": ObjectId(request_id)},
                {"$set": {"status": "rejected"}},
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
                "status": "rejected",
                "created_at": booking.get("created_at"),
            }
        )

    db["bookings"].delete_one({"_id": ObjectId(booking_id)})
    return redirect(url_for("admin.dashboard", msg="Booking deleted successfully"))

@admin_bp.route("/rejected")
def rejected():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    db = get_db()
    requests = list(db["booking_requests"].find({"status": "rejected"}).sort("date", -1))
    return render_template("admin_rejected.html", requests=requests)
