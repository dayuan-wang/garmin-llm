"""Deterministic descriptive metrics; interpretation is left to the calling LLM."""
import math
from collections import defaultdict
from datetime import date as Date, timedelta, datetime, timezone
from statistics import mean, median
from .data import collect, activities
from .catalog import date_range
from .garmin import GarminClient
from . import journal


def number(value, minimum=0):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= minimum else None


def get_path(row, path):
    for key in path.split('.'):
        if not isinstance(row,dict):
            return None
        row=row.get(key)
    return row


def series(rows, paths, scale=1):
    result = {}
    for row in rows:
        day = row.get('calendarDate')
        if not isinstance(day,str):
            continue
        for path in paths:
            value=number(get_path(row,path))
            if value is not None:
                result[day] = value*scale
                break
    return [{'date':d,'value':round(v,3)} for d,v in sorted(result.items())]


def describe(points, start_date, end_date, unit):
    expected=date_range(start_date,end_date)
    filtered=[p for p in points if start_date <= p['date'] <= end_date]
    vals=[p['value'] for p in filtered]
    return {'unit':unit,'observed_days':len(vals),'expected_days':expected,
            'missing_days':expected-len(vals),'mean':round(mean(vals),3) if vals else None,
            'median':round(median(vals),3) if vals else None,'min':min(vals) if vals else None,
            'max':max(vals) if vals else None,'series':filtered}


def summarize_activities(rows):
    sports=defaultdict(list)
    for row in rows:
        kind=row.get('activityType',{})
        key=kind.get('typeKey','unknown') if isinstance(kind,dict) else str(kind)
        sports[key].append(row)
    summaries={}
    for sport,items in sports.items():
        distances=[number(r.get('distance')) for r in items]
        durations=[number(r.get('duration')) for r in items]
        paired=[(d,t) for d,t in zip(distances,durations) if d is not None and d>0 and t is not None and t>0]
        summaries[sport]={'activities':len(items),
            'distance_km':round(sum(d for d in distances if d is not None)/1000,3) if any(d is not None for d in distances) else None,
            'duration_minutes':round(sum(t for t in durations if t is not None)/60,2) if any(t is not None for t in durations) else None,
            'missing_distance_count':sum(d is None for d in distances),
            'missing_duration_count':sum(t is None for t in durations),
            'pace_seconds_per_km':round(sum(t for d,t in paired)/(sum(d for d,t in paired)/1000),1)
                if paired and 'running' in sport else None}
    return summaries


def strength_progress(logs, exercise=None):
    grouped=defaultdict(list)
    for log in logs:
        workout=log['data']
        by_exercise=defaultdict(list)
        for item in workout.get('sets',[]):
            name=item['exercise'].strip().casefold()
            if exercise and name != exercise.strip().casefold():
                continue
            # Bodyweight and assistance are different quantities; never sum with external load.
            key=(name,item['load_type'])
            by_exercise[key].append(item)
        for (name,kind),sets in by_exercise.items():
            loads=[s['weight']*(0.45359237 if s['unit']=='lb' else 1) for s in sets]
            estimates=[w*(1+s['reps']/30) for w,s in zip(loads,sets) if kind=='external' and w>0 and s['reps']<=10]
            grouped[(name,kind)].append({'date':workout['date'],'log_id':log['id'],'sets':len(sets),
                'reps':sum(s['reps'] for s in sets),'max_recorded_load_kg':round(max(loads),3),
                'external_volume_kg_reps':round(sum(w*s['reps'] for w,s in zip(loads,sets)),2) if kind=='external' else None,
                'estimated_1rm_kg':round(max(estimates),2) if estimates else None})
    output=[]
    for (name,kind),sessions in sorted(grouped.items()):
        sessions.sort(key=lambda r:(r['date'],r['log_id']))
        output.append({'exercise':name,'load_type':kind,'sessions':sessions,
                       'recorded_load_change_kg':round(sessions[-1]['max_recorded_load_kg']-sessions[0]['max_recorded_load_kg'],3)
                       if len(sessions)>1 else None})
    return {'source':'local_journal','exercises':output,
            'method':'External volume = sum(weight_kg × reps). Estimated 1RM uses Epley only for external-load sets of 1–10 reps; it is an estimate, not a measured maximum.',
            'limitations':['Compare the same exercise, equipment, range of motion and load convention.',
                            'Assisted/bodyweight loads are reported separately; decreasing assistance can indicate progress.',
                            'Missing logs are not missed workouts.']}


def overview(start_date,end_date,*,demo=False):
    date_range(start_date,end_date,90)
    client=GarminClient()
    datasets={name:collect(name,start_date,end_date,demo=demo,client=client)
              for name in ('steps','sleep_summaries','daily_summaries','hrv_summaries')}
    activity_data=activities(start_date,end_date,demo=demo,client=client)
    specs={
        'steps':('steps',['totalSteps'],1,'steps'),
        'sleep_hours':('sleep_summaries',['sleepTimeSeconds'],1/3600,'hours'),
        'sleep_score':('sleep_summaries',['sleepScores.overall.value'],1,'Garmin score'),
        'resting_heart_rate':('daily_summaries',['heartRate.restingValue','restingHeartRate'],1,'bpm'),
        'stress':('daily_summaries',['stress.avgLevel','averageStressLevel'],1,'Garmin score'),
        'body_battery_max':('daily_summaries',['bodyBattery.maxValue','bodyBatteryHighestValue'],1,'Garmin score'),
        'hrv_ms':('hrv_summaries',['lastNightAvg','hrvSummary.lastNightAvg'],1,'ms'),
    }
    metrics={name:describe(series(datasets[ds]['rows'],paths,scale),start_date,end_date,unit)
             for name,(ds,paths,scale,unit) in specs.items()}
    logs=[] if demo else journal.read('workout',start_date,end_date)
    incomplete=any(not d['complete'] for d in datasets.values()) or not activity_data['complete']
    has_data=any(m['observed_days'] for m in metrics.values()) or bool(activity_data['data']) or bool(logs)
    return {'source':'demo' if demo else 'garmin_and_local_journal',
            'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'start_date':start_date,'end_date':end_date,
            'status':('partial' if has_data else 'error') if incomplete else ('ok' if has_data else 'no_data'),
            'metrics':metrics,'activities':activity_data,'sports':summarize_activities(activity_data['data']),
            'workout_logs':logs,'strength':strength_progress(logs),
            'availability':{name:{'status':d['status'],'complete':d['complete'],
                'errors':[c['error'] for c in d['chunks'] if 'error' in c]} for name,d in datasets.items()},
            'limitations':['Wearable estimates are not diagnoses. Missing values are excluded, never filled with zero.',
                'Activity totals may be incomplete when complete=false; daily series report observed coverage.',
                'Garmin calendar dates are preserved; sleep is associated with the date Garmin returns.',
                'No proprietary readiness or injury-risk score is inferred.']}


def compare_periods(report):
    end=Date.fromisoformat(report['end_date'])
    recent_start=str(end-timedelta(days=6))
    previous_start=str(end-timedelta(days=13))
    previous_end=str(end-timedelta(days=7))
    output={}
    for name,m in report['metrics'].items():
        recent=[p['value'] for p in m['series'] if recent_start<=p['date']<=str(end)]
        previous=[p['value'] for p in m['series'] if previous_start<=p['date']<=previous_end]
        output[name]={'recent_observed_days':len(recent),'previous_observed_days':len(previous),
            'recent_mean':round(mean(recent),3) if recent else None,
            'previous_mean':round(mean(previous),3) if previous else None,
            'difference':round(mean(recent)-mean(previous),3) if recent and previous else None,
            'unit':m['unit']}
    return {'recent':[recent_start,str(end)],'previous':[previous_start,previous_end],'metrics':output,
            'caution':'Descriptive differences over observed days, not causal effects or readiness judgments.'}
