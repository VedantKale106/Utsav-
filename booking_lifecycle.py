from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError


BOOKING_STATUSES = {"pending", "accepted", "rejected", "cancelled", "expired", "completed"}
ACTIVE_REQUEST_STATUSES = {"pending", "accepted"}


def utc_now():
    return datetime.now(timezone.utc)


def normalize_phone(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:]
    return digits


def reservation_keys(date_value, slot):
    if slot == "full_day":
        return [f"{date_value}:full_day", f"{date_value}:morning", f"{date_value}:afternoon", f"{date_value}:evening"]
    return [f"{date_value}:{slot}", f"{date_value}:full_day"]


def has_reservation(db, date_value, slot):
    reservation = db["calendar_reservations"].find_one({"_id": date_value})
    if not reservation:
        return False
    if reservation.get("full_day_owner"):
        return True
    if slot == "full_day":
        return bool(reservation.get("slots"))
    return any(item.get("slot") == slot for item in reservation.get("slots", []))


def reservation_owned(db, date_value, slot, owner_id):
    reservation = db["calendar_reservations"].find_one({"_id": date_value})
    if not reservation:
        return False
    if slot == "full_day":
        return reservation.get("full_day_owner") == owner_id
    return any(item.get("slot") == slot and item.get("owner_id") == owner_id for item in reservation.get("slots", []))


def reserve_slot(db, date_value, slot, owner_id):
    collection = db["calendar_reservations"]
    try:
        if slot == "full_day":
            result = collection.update_one(
                {"_id": date_value, "full_day_owner": {"$exists": False}, "slots": {"$size": 0}},
                {"$set": {"full_day_owner": owner_id}},
                upsert=True,
            )
        else:
            result = collection.update_one(
                {"_id": date_value, "full_day_owner": {"$exists": False}, "slots.slot": {"$ne": slot}},
                {"$push": {"slots": {"slot": slot, "owner_id": owner_id}}},
                upsert=True,
            )
        return result.modified_count == 1 or result.upserted_id is not None
    except DuplicateKeyError:
        return False


def release_slot(db, date_value, slot, owner_id=None):
    collection = db["calendar_reservations"]
    if slot == "full_day":
        query = {"_id": date_value, "full_day_owner": owner_id} if owner_id else {"_id": date_value}
        collection.update_one(query, {"$unset": {"full_day_owner": ""}})
    else:
        query = {"_id": date_value}
        if owner_id:
            query["slots"] = {"$elemMatch": {"slot": slot, "owner_id": owner_id}}
        collection.update_one(query, {"$pull": {"slots": {"slot": slot, **({"owner_id": owner_id} if owner_id else {})}}})
    reservation = collection.find_one({"_id": date_value})
    if reservation and not reservation.get("full_day_owner") and not reservation.get("slots"):
        collection.delete_one({"_id": date_value})


def expire_pending_requests(db, now=None):
    now = now or utc_now()
    result = db["booking_requests"].update_many(
        {"status": "pending", "expires_at": {"$lt": now}},
        {"$set": {"status": "expired", "status_updated_at": now}},
    )
    expired = list(db["booking_requests"].find({"status": "expired", "status_updated_at": now}, {"date": 1, "slot": 1, "_id": 1}))
    for item in expired:
        release_slot(db, item.get("date", ""), item.get("slot", ""), str(item["_id"]))
    return result.modified_count


def request_expiry(hours):
    return utc_now() + timedelta(hours=max(1, min(int(hours), 168)))
