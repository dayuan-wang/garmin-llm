"""Verified Personal API GET allowlist; Swagger inspected 2026-10-23.

No arbitrary URLs, Garmin mutations, or credentials are exposed to the model.
"""
from datetime import date as Date
from urllib.parse import urlencode

SOURCE = 'https://developer.garmin.com/gc-developer-program/personal/swagger-docs/'
# kind: range path, range query, single path, single query, static, activity, search
DATASETS = {
    'steps': ('range', '/usersummary-service/stats/steps/daily/{start_date}/{end_date}', 'Daily steps, distance and goals'),
    'stress': ('range', '/usersummary-service/stats/stress/daily/{start_date}/{end_date}', 'Daily stress'),
    'hydration': ('range', '/usersummary-service/stats/hydration/daily/{start_date}/{end_date}', 'Hydration'),
    'weight_goals': ('range', '/goal-service/goal/user/effective/weightgoal/{start_date}/{end_date}', 'Effective weight goals'),
    'weight': ('range', '/weight-service/weight/range/{start_date}/{end_date}', 'Weight and body composition summaries'),
    'weight_entries': ('range', '/weight-service/weight/all/{start_date}/{end_date}', 'All weight entries'),
    'sleep_summaries': ('range_query', '/sleep-service/sleep/dailySleepSummariesByDate', 'Sleep duration, stages, scores and naps'),
    'body_battery': ('range_query', '/wellness-service/wellness/bodyBattery/reports/daily', 'Body Battery reports'),
    'daily_summaries': ('range_query', '/usersummary-service/v2/dailysummaries', 'Steps, calories, heart rate, stress, respiration, SpO2 and intensity minutes'),
    'hrv_summaries': ('range', '/hrv-service/hrv/daily/{start_date}/{end_date}', 'HRV daily summaries and baseline'),
    'wellness_activities': ('range', '/wellnessactivity-service/activity/summary/range/{start_date}/{end_date}', 'Wellness activity summaries'),
    'sleep': ('day_query', '/sleep-service/sleep/dailySleep', 'Detailed sleep for one date'),
    'heart_rate': ('day_query', '/wellness-service/wellness/dailyHeartRate', 'Daily heart-rate measurements'),
    'daily_summary': ('day_query', '/usersummary-service/usersummary/daily', 'Daily wellness summary'),
    'hrv': ('day', '/hrv-service/hrv/{date}', 'Detailed HRV'),
    'food_logs': ('day', '/nutrition-service/food/logs/{date}', 'Food and nutrition logs'),
    'spo2': ('day', '/wellness-service/wellness/daily/spo2acclimation/{date}', 'Blood oxygen and acclimation'),
    'fitness_age': ('day', '/fitnessage-service/fitnessage/v2/{date}', 'Garmin fitness age'),
    'menstrual_summary': ('day', '/periodichealth-service/menstrualcycle/summary/{date}', 'Menstrual cycle summary; only request when relevant'),
    'menstrual_day': ('day', '/periodichealth-service/menstrualcycle/dayview/{date}', 'Detailed menstrual day view; requires today_date'),
    'profile': ('static', '/userprofile-service/userprofile/settings', 'Garmin profile settings'),
    'heart_rate_zones': ('static', '/biometric-service/heartRateZones/v2', 'Configured heart-rate zones'),
    'activities': ('search', '/activitylist-service/activities/search/activities', 'Activity search with filters and pagination'),
    'activity': ('activity', '/activity-service/activity/{activity_id}', 'Activity summary, metadata, measurements and splits'),
    'activity_workouts': ('activity', '/activity-service/activity/{activity_id}/workouts', 'Workout steps associated with an activity'),
}
# 25 JSON GET routes plus this binary GET route.
DOWNLOAD_PATH = '/download-service/files/activity/{activity_id}'
# Conservative per-request windows; steps/stress are limited to 28 days.
RANGE_LIMITS = {'steps': 28, 'stress': 28}


def range_limit(dataset):
    return RANGE_LIMITS.get(dataset, 31)


def valid_date(value):
    if not isinstance(value, str):
        raise ValueError('date must be a valid YYYY-MM-DD calendar date')
    try:
        if Date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise ValueError('date must be a valid YYYY-MM-DD calendar date') from None
    return value


def date_range(start, end, maximum=366):
    valid_date(start)
    valid_date(end)
    days = (Date.fromisoformat(end) - Date.fromisoformat(start)).days + 1
    if not 1 <= days <= maximum:
        raise ValueError(f'Date range must be ordered and include 1–{maximum} days')
    return days


def positive_id(value):
    value = str(value)
    if not value.isascii() or not value.isdigit() or int(value) <= 0 or len(value) > 20:
        raise ValueError('activity_id must be a positive numeric Garmin activity ID')
    return value


def build_request(dataset, date=None, start_date=None, end_date=None,
                  activity_id=None, start=0, limit=50, activity_type=None, today_date=None):
    if dataset not in DATASETS:
        raise ValueError('Unknown dataset; call list_data_types first')
    kind, path, _ = DATASETS[dataset]
    query = {}
    if kind.startswith('range'):
        start_date = start_date or date
        end_date = end_date or date or start_date
        date_range(start_date, end_date, range_limit(dataset))
        if kind == 'range_query':
            query.update(startDate=start_date, endDate=end_date)
        else:
            path = path.format(start_date=start_date, end_date=end_date)
    elif kind.startswith('day'):
        valid_date(date)
        if kind == 'day_query':
            query['calendarDate' if dataset == 'daily_summary' else 'date'] = date
        else:
            path = path.format(date=date)
    elif kind == 'activity':
        path = path.format(activity_id=positive_id(activity_id))
    elif kind == 'search':
        if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start <= 100000:
            raise ValueError('start must be between 0 and 100000')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')
        if bool(start_date) != bool(end_date):
            raise ValueError('Provide both start_date and end_date')
        if start_date:
            date_range(start_date, end_date)
            query.update(startDate=start_date, endDate=end_date)
        query.update(start=start, limit=limit)
        if activity_type:
            if len(activity_type) > 80 or not all(c.isalnum() or c == '_' for c in activity_type):
                raise ValueError('activity_type must be a Garmin type key, e.g. running')
            query['activityType'] = activity_type
    if dataset == 'weight':
        query['includeAll'] = 'true'
    if dataset == 'menstrual_day':
        query['todayDate'] = valid_date(today_date)
    return path + ('?' + urlencode(query) if query else '')
