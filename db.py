import os
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure

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

    return _db
