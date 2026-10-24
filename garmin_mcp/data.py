"""Bounded data retrieval, partial failures, and synthetic fixtures."""
from datetime import date as Date, timedelta, datetime, timezone
from .catalog import DATASETS, build_request, date_range, range_limit
from .garmin import GarminClient, GarminError


def records(data):
    """Recognize only known response envelopes; never recursively count nested samples."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ('data', 'dailySleepDTO', 'dailyWeightSummaries', 'dateWeightList', 'hrvSummaries'):
            if key in data:
                return records(data[key])
        return [data] if data else []
    return []


def result(dataset, data, demo=False, **meta):
    return {'source': 'demo' if demo else 'garmin', 'dataset': dataset,
            'status': 'no_data' if data in (None, [], {}) or (isinstance(data, dict) and data.get('data') == []) else 'ok',
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'data': data, **meta}


def synthetic(dataset, date=None, start_date=None, end_date=None, activity_id=None, **kwargs):
    first = start_date or date or '2026-10-22'
    last = end_date or first
    days = [str(Date.fromisoformat(first) + timedelta(days=i))
            for i in range((Date.fromisoformat(last)-Date.fromisoformat(first)).days+1)]
    if dataset == 'steps':
        return [{'calendarDate': d, 'totalSteps': 4321, 'stepGoal': 10000} for d in days]
    if dataset in ('sleep', 'sleep_summaries'):
        rows = [{'calendarDate': d, 'sleepTimeSeconds': 27000, 'deepSleepSeconds': 5400,
                 'sleepScores': {'overall': {'value': 80}}} for d in days]
        return rows[0] if dataset == 'sleep' else rows
    if dataset in ('daily_summaries', 'daily_summary'):
        rows = [{'calendarDate': d, 'heartRate': {'restingValue': 55},
                 'stress': {'avgLevel': 30}, 'bodyBattery': {'maxValue': 85}} for d in days]
        return rows[0] if dataset == 'daily_summary' else {'data': rows}
    if dataset == 'activities':
        kind = kwargs.get('activity_type') or 'running'
        rows = [{'activityId': 1000+i, 'activityName': 'Synthetic '+kind, 'startTimeLocal': d+' 08:00:00',
                 'activityType': {'typeKey': kind}, 'distance': 5000 if kind == 'running' else None, 'duration': 1800,
                 'averageHR': 140} for i,d in enumerate(days) if i % 2 == 0]
        start, limit = kwargs.get('start', 0), kwargs.get('limit', 50)
        return rows[start:start+limit]
    if dataset == 'activity':
        return {'activityId': int(activity_id), 'summaryDTO': {'distance': 5000, 'duration': 1800}}
    if dataset == 'heart_rate':
        return {'calendarDate': first, 'restingHeartRate': 55, 'maxHeartRate': 155}
    if dataset == 'hrv_summaries':
        return [{'calendarDate': d, 'lastNightAvg': 50, 'status': 'BALANCED'} for d in days]
    return []  # No fabricated device coverage; unsupported demo datasets explicitly have no data.


def query(dataset, *, demo=False, client=None, **params):
    # Validate before credentials/network, including in demo mode.
    path = build_request(dataset, **params)
    data = synthetic(dataset, **params) if demo else (client or GarminClient()).get(path)
    return result(dataset, data, demo, query={k:v for k,v in params.items() if v is not None})


def collect(dataset, start_date, end_date, *, demo=False, client=None):
    date_range(start_date, end_date)
    if DATASETS[dataset][0] not in ('range', 'range_query'):
        raise ValueError('This dataset is not a range endpoint')
    client = client or GarminClient()
    chunks, merged, cursor = [], [], Date.fromisoformat(start_date)
    end = Date.fromisoformat(end_date)
    while cursor <= end:
        until = min(cursor + timedelta(days=range_limit(dataset)-1), end)
        try:
            item = query(dataset, start_date=str(cursor), end_date=str(until), demo=demo, client=client)
            merged.extend(records(item['data']))
        except GarminError as exc:
            item = {'status': 'error', 'error': {'code': exc.code, 'message': str(exc)}, 'data': None}
        chunks.append({'start_date': str(cursor), 'end_date': str(until), **item})
        if item.get('error', {}).get('code') in ('access_denied', 'rate_limited', 'connection_error'):
            break
        cursor = until + timedelta(days=1)
    errors = any(c['status'] == 'error' for c in chunks)
    # Original raw responses are preserved in chunks. Rows provide known envelope unwrapping.
    return {'source': 'demo' if demo else 'garmin', 'dataset': dataset,
            'start_date': start_date, 'end_date': end_date,
            'status': ('partial' if merged else 'error') if errors else ('ok' if merged else 'no_data'),
            'rows': merged, 'chunks': chunks, 'complete': not errors}


def activities(start_date, end_date, *, activity_type=None, max_records=500, demo=False, client=None):
    date_range(start_date, end_date)
    if not 1 <= max_records <= 1000:
        raise ValueError('max_records must be 1–1000')
    client = client or GarminClient()
    rows, seen, offset = [], set(), 0
    while len(rows) < max_records:
        limit = min(100, max_records-len(rows))
        try:
            item = query('activities', start_date=start_date, end_date=end_date,
                         activity_type=activity_type, start=offset, limit=limit, demo=demo, client=client)
            page = item['data']
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                raise GarminError('Unexpected activity list shape', 'invalid_response')
        except GarminError as exc:
            return {'status': 'partial' if rows else 'error', 'data': rows, 'complete': False,
                    'source': 'demo' if demo else 'garmin', 'error': {'code': exc.code, 'message': str(exc)}}
        for row in page:
            key = str(row.get('activityId', ''))
            if not key or key not in seen:
                rows.append(row)
                seen.add(key)
        offset += len(page)
        if len(page) < limit:
            return {**result('activities', rows, demo), 'complete': True, 'next_start': None}
        if not page:
            break
        # Offset advances even if Garmin repeats an activity; bounded independently of deduplication.
        if offset >= max_records:
            break
    return {**result('activities', rows, demo), 'complete': False, 'next_start': offset,
            'warning': 'Record cap reached; narrow dates or use paginated get_garmin_data before claiming completeness'}
