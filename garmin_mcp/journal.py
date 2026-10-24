"""Local, versioned training journal. Nothing here writes to Garmin."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .catalog import valid_date, date_range

DATA_DIR = Path(__file__).resolve().parents[1] / '.data'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ExerciseSet(StrictModel):
    exercise: str = Field(min_length=1, max_length=100)
    reps: int = Field(ge=1, le=1000, strict=True)
    weight: float = Field(ge=0, le=2000)
    unit: Literal['kg', 'lb'] = 'kg'
    load_type: Literal['external', 'bodyweight', 'assisted'] = 'external'
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str = Field(default='', max_length=1000)


class WorkoutLog(StrictModel):
    date: str
    sport: str = Field(min_length=1, max_length=60)
    activity_id: str | None = Field(default=None, pattern=r'^[1-9][0-9]{0,19}$')
    duration_minutes: float | None = Field(default=None, gt=0, le=2880)
    session_rpe: float | None = Field(default=None, ge=1, le=10)
    sets: list[ExerciseSet] = Field(default_factory=list, max_length=300)
    notes: str = Field(default='', max_length=5000)

    @model_validator(mode='after')
    def validate_day(self):
        valid_date(self.date)
        return self


class CoachProfile(StrictModel):
    timezone: str = 'America/New_York'
    goals: list[str] = Field(default_factory=list, max_length=20)
    available_days: list[Literal['Mon','Tue','Wed','Thu','Fri','Sat','Sun']] = Field(default_factory=list, max_length=7)
    minutes_per_session: int | None = Field(default=None, ge=5, le=600)
    equipment: list[str] = Field(default_factory=list, max_length=50)
    experience: str = Field(default='', max_length=2000)
    limitations: str = Field(default='', max_length=2000)
    preferences: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_timezone(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError('Use an IANA timezone such as America/New_York') from None
        if len(self.available_days) != len(set(self.available_days)):
            raise ValueError('available_days must be unique')
        return self


class PlanSession(StrictModel):
    date: str
    sport: str = Field(min_length=1, max_length=60)
    duration_minutes: int = Field(ge=0, le=600)
    description: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def validate_day(self):
        valid_date(self.date)
        return self


class TrainingPlan(StrictModel):
    goal: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=6000)
    evidence_start: str
    evidence_end: str
    sessions: list[PlanSession] = Field(min_length=1, max_length=120)
    status: Literal['draft', 'accepted'] = 'draft'
    assumptions: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def validate_evidence(self):
        date_range(self.evidence_start, self.evidence_end)
        return self


def record_id(value):
    if not value or len(value) > 100 or not all(c.isascii() and (c.isalnum() or c in '-_') for c in value):
        raise ValueError('record_id must contain 1–100 ASCII letters, digits, hyphens or underscores')
    return value


@contextmanager
def database(root=None):
    root = Path(root) if root else DATA_DIR
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / 'coach.sqlite3'
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, date TEXT, payload TEXT, revision INTEGER, updated_at TEXT, PRIMARY KEY(kind,id))')
        conn.execute('CREATE TABLE IF NOT EXISTS history (kind TEXT, id TEXT, revision INTEGER, payload TEXT, updated_at TEXT, PRIMARY KEY(kind,id,revision))')
        yield conn
        conn.commit()
    finally:
        conn.close()


def save(kind, identifier, payload, *, replace=False, root=None):
    record_id(identifier)
    # All callers validate with the kind's model, including direct library callers.
    model = {'workout': WorkoutLog, 'profile': CoachProfile, 'plan': TrainingPlan}.get(kind)
    if model is None:
        raise ValueError('Unknown journal kind')
    payload = model.model_validate(payload).model_dump()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(encoded.encode()) > 150000:
        raise ValueError('Record too large')
    now = datetime.now(timezone.utc).isoformat()
    with database(root) as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT payload,revision FROM records WHERE kind=? AND id=?', (kind,identifier)).fetchone()
        if old and old[0] == encoded:
            return {'source':'local_journal','id':identifier,'revision':old[1],'status':'unchanged'}
        if old and not replace:
            raise ValueError('Record already exists with different content; use replace=true for an explicit correction')
        rev = old[1]+1 if old else 1
        conn.execute('INSERT INTO history VALUES (?,?,?,?,?)', (kind,identifier,rev,encoded,now))
        conn.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?)',
                     (kind,identifier,payload.get('date',''),encoded,rev,now))
    return {'source':'local_journal','id':identifier,'revision':rev,'status':'saved','garmin_modified':False}


def read(kind, start_date=None, end_date=None, *, root=None):
    if start_date or end_date:
        date_range(start_date,end_date,3660)
    path = (Path(root) if root else DATA_DIR) / 'coach.sqlite3'
    if not path.exists():
        return []
    with database(root) as conn:
        sql = 'SELECT id,payload,revision,updated_at FROM records WHERE kind=?'
        args = [kind]
        if start_date:
            sql += ' AND date BETWEEN ? AND ?'
            args.extend([start_date,end_date])
        rows = conn.execute(sql+' ORDER BY date,id',args).fetchall()
    return [{'id':r[0],'data':json.loads(r[1]),'revision':r[2],'updated_at':r[3]} for r in rows]
