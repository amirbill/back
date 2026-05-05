from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VolsSourceStat(BaseModel):
    name: str
    area: str
    total: int = 0
    matched: int = 0
    updatedAt: Optional[int] = None
    ok: bool = True
    status: Optional[int] = None


class LiveFlightRecord(BaseModel):
    hex: str
    flight: Optional[str] = None
    r: Optional[str] = None
    t: Optional[str] = None
    desc: Optional[str] = None
    route: Optional[str] = None
    depAirport: Optional[str] = None
    arrAirport: Optional[str] = None
    routeDataSource: Optional[str] = None
    routeSourceUpdatedAt: Optional[int] = None
    dataSource: Optional[str] = None
    sourceArea: Optional[str] = None
    sourceUpdatedAt: Optional[int] = None
    capturedAt: Optional[int] = None
    alt_baro: Optional[Any] = None
    alt_geom: Optional[float] = None
    gs: Optional[float] = None
    track: Optional[float] = None
    true_heading: Optional[float] = None
    baro_rate: Optional[float] = None
    squawk: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    seen: Optional[float] = None
    seen_pos: Optional[float] = None
    messages: Optional[int] = None
    airline: Optional[str] = None


class LiveSnapshotIn(BaseModel):
    tunisair: List[LiveFlightRecord] = Field(default_factory=list)
    nouvelair: List[LiveFlightRecord] = Field(default_factory=list)
    total: int = 0
    timestamp: int
    sources: List[VolsSourceStat] = Field(default_factory=list)
    collector: str = "next-vols-live"


class HistoryFlightRecord(BaseModel):
    callsign: str
    icao24: str
    estDepartureAirport: Optional[str] = None
    estArrivalAirport: Optional[str] = None
    firstSeen: int
    lastSeen: int
    aircraftType: Optional[str] = None
    status: Optional[str] = None
    delayMin: Optional[int] = None
    delaySource: Optional[str] = None


class HistorySnapshotIn(BaseModel):
    flights: List[HistoryFlightRecord] = Field(default_factory=list)
    source: str
    timestamp: int
    collector: str = "next-vols-history"


class ScheduleArchiveFlight(BaseModel):
    callsign: str
    dep: Optional[str] = None
    arr: Optional[str] = None
    depHour: Optional[int] = None
    depMin: Optional[int] = None
    durMin: Optional[int] = None
    type: Optional[str] = None
    icao24: Optional[str] = None


class ScheduleArchiveIn(BaseModel):
    flights: List[ScheduleArchiveFlight] = Field(default_factory=list)
    source: str = "frontend-vols-data"
    version: str = "2026-05-05"
    timestamp: int
