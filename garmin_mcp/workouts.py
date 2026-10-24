"""Independent tools for activity type keys, with account-driven discovery.

These are Garmin activity records, not scheduled workout templates. Built-ins
are convenient filters, not an exhaustive or account-verified Garmin taxonomy.
"""
from typing import Any
import re
import sqlite3
from . import data, journal

BUILTIN_TYPES = (
    'running', 'trail_running', 'treadmill_running', 'track_running', 'virtual_run',
    'cycling', 'indoor_cycling', 'mountain_biking', 'gravel_cycling', 'virtual_ride',
    'lap_swimming', 'open_water_swimming', 'walking', 'hiking',
    'strength_training', 'indoor_cardio', 'hiit', 'yoga', 'pilates', 'elliptical',
    'stair_climbing', 'rowing', 'indoor_rowing', 'basketball', 'bouldering',
    'rock_climbing', 'tennis', 'skiing', 'snowboarding', 'stand_up_paddleboarding', 'kayaking',
)


def valid_type(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', value):
        raise ValueError('Activity type must be a lowercase Garmin type key, at most 48 characters')
    return value


def tool_name(key):
    return f'get_{valid_type(key)}_workouts'


def observed_types(rows):
    keys, invalid = set(), 0
    for row in rows:
        kind = row.get('activityType')
        try:
            keys.add(valid_type(kind.get('typeKey') if isinstance(kind, dict) else None))
        except ValueError:
            invalid += 1
    return sorted(keys), invalid


def remembered_types():
    path = journal.DATA_DIR / 'coach.sqlite3'
    if not path.exists():
        return []
    # Reading/discovery of tools never creates the journal or accesses Garmin.
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_types'").fetchone():
            return []
        return [valid_type(row[0]) for row in conn.execute('SELECT type_key FROM activity_types ORDER BY type_key')]


def remember_types(keys):
    validated = [valid_type(key) for key in keys]
    if not validated:
        return
    with journal.database() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS activity_types (type_key TEXT PRIMARY KEY)')
        conn.executemany('INSERT OR IGNORE INTO activity_types VALUES (?)', [(key,) for key in validated])


def query_type(key, start_date, end_date, *, max_records=500, demo=False, client=None):
    valid_type(key)
    result = data.activities(start_date, end_date, activity_type=key,
                             max_records=max_records, demo=demo, client=client)
    rows = result['data']
    # Some broad Garmin filters include child sports; each dedicated tool is exact.
    selected = [row for row in rows if isinstance(row.get('activityType'), dict)
                and row['activityType'].get('typeKey') == key]
    status = result['status']
    if result['complete']:
        status = 'ok' if selected else 'no_data'
    return {**result, 'status': status, 'data': selected, 'activity_type': key,
            'start_date': start_date, 'end_date': end_date, 'filter_mode': 'exact_type_key',
            'excluded_other_type_count': len(rows)-len(selected)}


def register_type(server, key, demo, annotations):
    def read_workouts(start_date: str, end_date: str, max_records: int = 500) -> dict[str, Any]:
        return query_type(key, start_date, end_date, max_records=max_records, demo=demo)
    server.add_tool(read_workouts, name=tool_name(key),
        description=f'Read {key.replace("_", " ")} activity records as JSON. '
        f'Exact Garmin activityType.typeKey={key}; child types are separate tools. '
        'Inclusive YYYY-MM-DD dates, at most 366 days; max_records 1–1000. '
        'Check complete before treating the result as all history. '
        'Raw records preserve sport-specific fields. An empty result does not prove no exercise.',
        annotations=annotations)
