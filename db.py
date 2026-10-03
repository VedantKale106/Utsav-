import os
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure
from booking_lifecycle import reserve_slot

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is not None:
        return _db

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is not set.")

    _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    _db = _client["utsav"]

    # Create a unique compound index on (date, slot) to prevent race-condition duplicates.
    # full_day bookings are handled at the application layer before insertion.
    bookings = _db["bookings"]
    bookings.create_index(
        [("date", ASCENDING), ("slot", ASCENDING)],
        unique=True,
        name="unique_date_slot",
    )
    _db["booking_requests"].create_index([("status", ASCENDING), ("expires_at", ASCENDING)])
    _db["booking_requests"].create_index([("phone_normalized", ASCENDING), ("date", ASCENDING), ("slot", ASCENDING)])
    _db["audit_logs"].create_index([("created_at", ASCENDING)])
    for booking in bookings.find({}, {"date": 1, "slot": 1, "request_id": 1}):
        reserve_slot(_db, booking.get("date", ""), booking.get("slot", ""), booking.get("request_id", str(booking.get("_id"))))
    anonymize_old_data(_db)

    return _db


def anonymize_old_data(db=None):
    if db is None:
        db = get_db()
    retention_days = int(os.getenv("DATA_RETENTION_DAYS", "730"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(30, retention_days))
    db["booking_requests"].update_many(
        {"status": {"$in": ["rejected", "cancelled", "expired", "completed"]}, "created_at": {"$lt": cutoff.isoformat()}},
        {"$set": {"name": "[anonymized]", "phone": "[anonymized]", "phone_normalized": "[anonymized]", "event_type": "[anonymized]"}, "$unset": {"status_token": ""}},
    )
    db["audit_logs"].delete_many({"created_at": {"$lt": cutoff}})
