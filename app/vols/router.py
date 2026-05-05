from fastapi import APIRouter, HTTPException

from app.vols import service
from app.vols.schemas import HistorySnapshotIn, LiveSnapshotIn, ScheduleArchiveIn


router = APIRouter()


@router.post("/live-snapshots")
async def create_live_snapshot(payload: LiveSnapshotIn):
    try:
        return await service.store_live_snapshot(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/history-snapshots")
async def create_history_snapshot(payload: HistorySnapshotIn):
    try:
        return await service.store_history_snapshot(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/schedule-archives")
async def create_schedule_archive(payload: ScheduleArchiveIn):
    try:
        return await service.store_schedule_archive(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/live-snapshots/latest")
async def read_latest_live_snapshot():
    try:
        return await service.get_latest_snapshot(service.LIVE_COLLECTION)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history-snapshots/latest")
async def read_latest_history_snapshot():
    try:
        return await service.get_latest_snapshot(service.HISTORY_COLLECTION)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/schedule-archives/latest")
async def read_latest_schedule_archive():
    try:
        return await service.get_latest_snapshot(service.SCHEDULE_COLLECTION)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

