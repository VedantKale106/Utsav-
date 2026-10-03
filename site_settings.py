import json
from copy import deepcopy
from pathlib import Path


SETTINGS_PATH = Path(__file__).with_name("site_settings.json")
with SETTINGS_PATH.open(encoding="utf-8") as settings_file:
    DEFAULT_SETTINGS = json.load(settings_file)

_cached_settings = None


def get_site_settings():
    global _cached_settings
    if _cached_settings is not None:
        return deepcopy(_cached_settings)

    _cached_settings = deepcopy(DEFAULT_SETTINGS)
    return deepcopy(_cached_settings)


def clear_settings_cache():
    global _cached_settings
    _cached_settings = None


def active_slots(settings=None):
    settings = settings or get_site_settings()
    return [slot for slot in settings["slots"] if slot.get("active", True)]


def slots_by_key(settings=None):
    return {slot["key"]: slot for slot in active_slots(settings)}
