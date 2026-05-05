from datetime import datetime, timezone
from typing import Any, Dict

from app.db.mongodb import get_database
from app.vols.schemas import HistorySnapshotIn, LiveSnapshotIn, ScheduleArchiveIn


AVIATION_DB_NAME = "aviation"
LIVE_COLLECTION = "vols_live_snapshots"
HISTORY_COLLECTION = "vols_history_snapshots"
SCHEDULE_COLLECTION = "vols_schedule_archives"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_aviation_db():
    db = get_database()
    client = db.client
    if client is None:
        return None
    return client[AVIATION_DB_NAME]


async def store_live_snapshot(payload: LiveSnapshotIn) -> Dict[str, Any]:
    aviation_db = _get_aviation_db()
    if aviation_db is None:
        return {"stored": False, "reason": "database_unavailable"}

    document = payload.model_dump()
    document["created_at"] = _utc_now()
    document["snapshot_key"] = str(payload.timestamp)

    collection = aviation_db[LIVE_COLLECTION]
    await collection.update_one(
        {"snapshot_key": document["snapshot_key"]},
        {"$set": document},
        upsert=True,
    )

    return {"stored": True, "collection": LIVE_COLLECTION, "snapshot_key": document["snapshot_key"]}


async def store_history_snapshot(payload: HistorySnapshotIn) -> Dict[str, Any]:
    aviation_db = _get_aviation_db()
    if aviation_db is None:
        return {"stored": False, "reason": "database_unavailable"}

    document = payload.model_dump()
    document["created_at"] = _utc_now()
    document["snapshot_key"] = f"{payload.source}-{payload.timestamp}"

    collection = aviation_db[HISTORY_COLLECTION]
    await collection.update_one(
        {"snapshot_key": document["snapshot_key"]},
        {"$set": document},
        upsert=True,
    )

    return {"stored": True, "collection": HISTORY_COLLECTION, "snapshot_key": document["snapshot_key"]}


async def store_schedule_archive(payload: ScheduleArchiveIn) -> Dict[str, Any]:
    aviation_db = _get_aviation_db()
    if aviation_db is None:
        return {"stored": False, "reason": "database_unavailable"}

    document = payload.model_dump()
    document["created_at"] = _utc_now()
    document["archive_key"] = f"{payload.source}-{payload.version}"

    collection = aviation_db[SCHEDULE_COLLECTION]
    await collection.update_one(
        {"archive_key": document["archive_key"]},
        {"$set": document},
        upsert=True,
    )

    return {"stored": True, "collection": SCHEDULE_COLLECTION, "archive_key": document["archive_key"]}


async def get_latest_snapshot(collection_name: str) -> Dict[str, Any]:
    aviation_db = _get_aviation_db()
    if aviation_db is None:
        return {}

    document = await aviation_db[collection_name].find_one(sort=[("timestamp", -1), ("created_at", -1)])
    if not document:
        return {}

    document["id"] = str(document.pop("_id"))
    return document

