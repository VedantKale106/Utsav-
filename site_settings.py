from copy import deepcopy

from db import get_db


DEFAULT_SETTINGS = {
    "business_name": "Utsav Banquet Hall",
    "address": "Satav Chowk, Baramati, Pune District, Maharashtra 413102",
    "phone": "+91 99999 99999",
    "email": "info@utsavbanquet.in",
    "pending_request_expiry_hours": 48,
    "blackout_dates": [],
    "map_embed_url": "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3789.4287447826!2d74.5726!3d18.1522!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3bc3830b1e4a5555%3A0xa9e6a4d55f1c0d55!2sSatav%20Chowk%2C%20Baramati%2C%20Maharashtra!5e0!3m2!1sen!2sin",
    "slots": [
        {"key": "morning", "label": "Morning", "time": "7 AM - 12 PM", "price": 25000, "description": "Perfect for engagement ceremonies, morning weddings, and religious functions.", "featured": False, "active": True},
        {"key": "afternoon", "label": "Afternoon", "time": "12 PM - 5 PM", "price": 20000, "description": "Ideal for daytime receptions, luncheons, and corporate gatherings.", "featured": False, "active": True},
        {"key": "evening", "label": "Evening", "time": "5 PM - 11 PM", "price": 35000, "description": "Our most sought-after slot - perfect for grand receptions and weddings.", "featured": True, "active": True},
        {"key": "full_day", "label": "Full Day", "time": "7 AM - 11 PM", "price": 70000, "description": "Complete day access for multi-ceremony events with ample setup time.", "featured": False, "active": True},
    ],
    "highlights": [
        {"title": "AC Hall", "description": "Centrally air-conditioned hall for all-season comfort"},
        {"title": "Ample Parking", "description": "Dedicated parking for 200+ vehicles"},
        {"title": "Decoration", "description": "Professional in-house decoration services"},
        {"title": "Catering", "description": "Curated menus with customizable catering options"},
    ],
    "stats": [
        {"value": "500+", "label": "Events Hosted"},
        {"value": "15+", "label": "Years of Excellence"},
        {"value": "1000", "label": "Guest Capacity"},
        {"value": "5", "label": "Star Rating"},
    ],
}

_cached_settings = None


def get_site_settings():
    global _cached_settings
    if _cached_settings is not None:
        return deepcopy(_cached_settings)

    settings = deepcopy(DEFAULT_SETTINGS)
    try:
        stored = get_db()["site_settings"].find_one({"_id": "main"})
        if stored:
            stored.pop("_id", None)
            settings.update(stored)
    except Exception:
        pass

    _cached_settings = settings
    return deepcopy(settings)


def save_site_settings(settings):
    global _cached_settings
    clean_settings = deepcopy(settings)
    get_db()["site_settings"].replace_one(
        {"_id": "main"},
        {"_id": "main", **clean_settings},
        upsert=True,
    )
    _cached_settings = clean_settings


def clear_settings_cache():
    global _cached_settings
    _cached_settings = None


def active_slots(settings=None):
    settings = settings or get_site_settings()
    return [slot for slot in settings["slots"] if slot.get("active", True)]


def slots_by_key(settings=None):
    return {slot["key"]: slot for slot in active_slots(settings)}
