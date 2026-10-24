"""One typed JSON MCP entry point per supported health dataset."""
from typing import Any
from .catalog import DATASETS
from . import data

# Preserve the original single-day get_steps API; history gets its own tool.
HEALTH_TOOLS = {name: ('get_steps_history' if name == 'steps' else 'get_'+name)
                for name, (kind, _, _) in DATASETS.items()
                if kind not in ('activity', 'search')}
EXISTING_TOOLS = {'sleep', 'heart_rate'}
SUMMARY_FIELDS = {
    'respiration': 'respiration', 'calories': 'calories',
    'intensity_minutes': 'intensityMinutes', 'movement': 'movement',
    'heart_rate_summary': 'heartRate',
}


def _summary_reader(name, field, demo):
    def read(start_date: str, end_date: str) -> dict[str, Any]:
        result = data.collect('daily_summaries', start_date, end_date, demo=demo)
        rows = [{'calendarDate':row.get('calendarDate'), 'data':row.get(field),
                 'status':'ok' if row.get(field) is not None else 'no_data'}
                for row in result['rows']]
        present = any(row['status']=='ok' for row in rows)
        status = ('ok' if present else 'no_data') if result['complete'] else ('partial' if present else 'error')
        return {'source':result['source'], 'dataset':name, 'status':status,
                'start_date':start_date, 'end_date':end_date, 'data':rows,
                'complete':result['complete'], 'upstream_dataset':'daily_summaries',
                'field':field, 'errors':[c['error'] for c in result['chunks'] if 'error' in c]}
    return read


def _range_reader(dataset, demo):
    def read(start_date: str, end_date: str) -> dict[str, Any]:
        result = data.collect(dataset, start_date, end_date, demo=demo)
        # Keep original chunks for provenance, with data as the consistent JSON list.
        return {**result, 'data': result['rows']}
    return read


def _day_reader(dataset, demo):
    def read(date: str) -> dict[str, Any]:
        return data.query(dataset, date=date, demo=demo)
    return read


def _menstrual_reader(demo):
    def read(date: str, today_date: str) -> dict[str, Any]:
        return data.query('menstrual_day', date=date, today_date=today_date, demo=demo)
    return read


def _static_reader(dataset, demo):
    def read() -> dict[str, Any]:
        return data.query(dataset, demo=demo)
    return read


def register_health_tools(server, demo, annotations):
    for dataset, name in HEALTH_TOOLS.items():
        if dataset in EXISTING_TOOLS:
            continue
        kind, _, description = DATASETS[dataset]
        if kind.startswith('range'):
            fn = _range_reader(dataset, demo)
            detail = ' Inclusive YYYY-MM-DD dates, at most 366 days; automatically split into bounded requests. Check complete and partial errors.'
        elif dataset == 'menstrual_day':
            fn = _menstrual_reader(demo)
            detail = ' Provide both date and today_date as YYYY-MM-DD; query only when relevant to the user.'
        elif kind.startswith('day'):
            fn = _day_reader(dataset, demo)
            detail = ' Provide a YYYY-MM-DD date.'
        else:
            fn = _static_reader(dataset, demo)
            detail = ' No date parameters.'
        server.add_tool(fn, name=name, description=description+'; original Garmin JSON.'+detail,
                        annotations=annotations)
    for name, field in SUMMARY_FIELDS.items():
        server.add_tool(_summary_reader(name, field, demo), name='get_'+name,
            description=f'Read daily {name.replace("_", " ")} as JSON over inclusive YYYY-MM-DD dates (<=366 days). '
                        f'Projects the original {field} object from daily_summaries, preserving Garmin units and nulls. '
                        'This is a filtered view of the documented daily-summary endpoint, not a separate Garmin API route.',
            annotations=annotations)
