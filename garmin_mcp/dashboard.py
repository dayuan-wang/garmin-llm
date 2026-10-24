"""Self-contained, interactive health snapshot. No CDNs or outbound requests."""
import html
import json
import os
import uuid
from pathlib import Path
from . import journal

ASSETS = Path(__file__).with_name('assets')


def _escape(value):
    return html.escape(str(value), quote=True)


def _view_data(report):
    """Include only chart/table fields, never embed account IDs or GPS coordinates."""
    fields = ('activityName', 'startTimeLocal', 'duration', 'distance', 'averageHR')
    activities = [{**{key: row.get(key) for key in fields},
                   'activityType': {'typeKey': (row.get('activityType') or {}).get('typeKey', 'unknown')}}
                  for row in report['activities']['data']]
    return {'start_date': report['start_date'], 'end_date': report['end_date'],
            'metrics': report['metrics'], 'activities': {'data': activities,
            'complete': report['activities']['complete']}}


def render(report):
    esc = _escape
    css = (ASSETS / 'dashboard.css').read_text(encoding='utf-8')
    js = (ASSETS / 'dashboard.js').read_text(encoding='utf-8')
    payload = json.dumps(_view_data(report), ensure_ascii=False, allow_nan=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    demo = '<div class="banner" role="status">SYNTHETIC DEMO — not your health data</div>' if report['source'] == 'demo' else ''
    if report['status'] not in ('ok', 'no_data'):
        demo += '<div class="banner" role="status">Some data could not be retrieved. Totals may be incomplete; check data coverage below.</div>'
    notes = ''.join(f'<div class="journal-note"><h3>{esc(row["data"]["date"])} · {esc(row["data"]["sport"].replace("_", " "))}</h3><small>{len(row["data"].get("sets", []))} logged sets</small><p>{esc(row["data"].get("notes", ""))}</p></div>' for row in report['workout_logs'])
    if not notes:
        notes = '<p class="empty">No workout notes yet. Ask your coach to record your exercises, sets, weights and how the session felt.</p>'
    strength = ''.join('<tr>' + ''.join('<td>' + esc(value if value is not None else '—') + '</td>' for value in
        (exercise['exercise'], exercise['load_type'], session['date'], session['sets'], session['reps'],
         session['max_recorded_load_kg'], session['external_volume_kg_reps'], session['estimated_1rm_kg'])) + '</tr>'
        for exercise in report['strength']['exercises'] for session in exercise['sessions'])
    coverage_labels = {'steps': 'Daily steps', 'sleep_summaries': 'Sleep', 'daily_summaries': 'Daily wellness', 'hrv_summaries': 'HRV'}
    coverage = ''.join(f'<div class="coverage-item">{esc(coverage_labels.get(k,k))}<strong>{esc(v["status"].replace("_", " "))}</strong></div>' for k,v in report['availability'].items())
    errors = ''.join('<li>'+esc(k)+': '+esc(e['message'])+'</li>' for k,v in report['availability'].items() for e in v.get('errors', []))
    if report['activities'].get('error'):
        errors += '<li>Activities: '+esc(report['activities']['error']['message'])+'</li>'
    limitations = ''.join('<li>'+esc(t)+'</li>' for t in report['limitations'])
    metric_tabs = ''.join(f'<button type="button" data-metric="{key}" aria-pressed="{str(i==0).lower()}">{label}</button>' for i,(key,label) in enumerate([
        ('sleep_hours','Sleep'), ('hrv_ms','HRV'), ('resting_heart_rate','Resting HR'), ('steps','Steps')]))
    stat_cards = ''.join(f'<div class="stat"><div class="stat-label">{label}</div><div class="stat-value" id="{identifier}">—</div><div class="stat-foot" id="{identifier}-foot">Available observations</div></div>' for label,identifier in [
        ('Average sleep','sleep-value'),('Recorded training','training-value'),('Average HRV','hrv-value'),('Resting heart rate','heart-value')])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>Garmin Learning · Your training rhythm</title><style>{css}</style></head>
<body><a class="skip" href="#main">Skip to dashboard</a>
<aside class="rail"><a href="#main" class="brand" aria-label="Garmin Learning home"><svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="10" fill="#3066db"/><path d="M5 18h5l3-8 6 15 3-9h5" stroke="white" stroke-width="2" fill="none" stroke-linejoin="round"/></svg><span>Garmin<small>Learning</small></span></a>
<nav aria-label="Dashboard sections"><a href="#main">Overview</a><a href="#trends">Health trends</a><a href="#activities">Activity log</a><a href="#journal">Training journal</a><a href="#coverage">Data coverage</a></nav>
<div class="rail-bottom"><strong>Your personal coach</strong>Health and training, in context.<br>Private snapshot · works offline</div></aside>
<main class="main" id="main"><header class="topbar"><span class="mobile-brand">Garmin Learning</span><span class="source"><i class="dot" aria-hidden="true"></i>{'Synthetic preview' if report['source']=='demo' else 'Garmin + your training journal'}</span><span class="pill">{esc(report['start_date'])} – {esc(report['end_date'])}</span></header>
{demo}<div class="heading"><div><h1>Your training rhythm.</h1><p class="subtitle">See how your sleep, daily health and training move together.</p></div><div class="period-controls" role="group" aria-label="Displayed date range"><button data-range="0" aria-pressed="true">Full period</button><button data-range="14" aria-pressed="false">Last 14 days</button><button data-range="7" aria-pressed="false">Last 7 days</button></div></div>
<noscript><p class="nojs">Enable JavaScript for interactive charts and the activity table. Your journal and data coverage remain available below.</p></noscript>
<div class="stats" aria-live="polite">{stat_cards}</div>
<div class="chart-layout" id="trends"><section class="panel"><div class="panel-head"><div><h2>Recovery & training</h2><p id="selected-dates">{esc(report['start_date'])} – {esc(report['end_date'])}</p></div></div><div class="metric-tabs" role="group" aria-label="Health metric">{metric_tabs}</div><div class="chart" id="timeline"></div><div class="chart-foot"><div class="legend"><span id="metric-legend">Sleep duration</span><span>Recorded training</span></div><span id="chart-coverage"></span></div><p class="note">Separate scales. Gaps mean no observation; a day without a recorded session does not prove inactivity.</p></section>
<aside class="panel summary-panel"><div class="panel-head"><div><h2>The latest week</h2><p id="comparison-dates"></p></div></div><div id="comparisons" style="display:contents"></div><p class="note">Fixed comparison of the last two weeks in this snapshot. Changes describe observations; they are not a readiness score.</p></aside></div>
<section class="section"><div class="split"><div class="panel"><div class="panel-head"><div><h2>Where your time went</h2><p>Recorded duration by sport</p></div></div><div id="sports"></div><p class="note">* Some sessions have no recorded duration.</p></div><div class="panel"><div class="panel-head"><div><h2>Daily health, at a glance</h2><p>Averages over the selected period</p></div></div><div class="detail-metrics" id="more-metrics"></div></div></div></section>
<section class="section" id="activities"><div class="section-title"><div><h2>Activity log</h2><p id="activity-count"></p></div><label><span class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden">Filter activities by sport</span><select id="sport-filter" class="filter"><option value="">All sports</option></select></label></div><div class="panel"><div class="table-wrap"><table><thead><tr><th scope="col">Local date</th><th scope="col">Activity</th><th scope="col">Duration</th><th scope="col">Distance</th><th scope="col">Average HR</th></tr></thead><tbody id="activity-rows"></tbody></table></div><p class="note">Dates use Garmin's local activity timestamps. Distance is shown for running, cycling, swimming and walking. Retrieval complete: {esc(report['activities']['complete'])}.</p></div></section>
<section class="section" id="journal"><div class="section-title"><div><h2>Your training journal</h2><p>The context your watch cannot capture.</p></div></div><div class="panel">{notes}<details><summary>Strength progression</summary><div class="table-wrap"><table><thead><tr><th>Exercise</th><th>Load type</th><th>Date</th><th>Sets</th><th>Reps</th><th>Max kg</th><th>kg × reps</th><th>Estimated 1RM kg</th></tr></thead><tbody>{strength or '<tr><td colspan="8" class="empty">Log weighted sets to start comparing your sessions.</td></tr>'}</tbody></table></div><p>{esc(report['strength']['method'])}</p></details></div></section>
<section class="section" id="coverage"><div class="panel"><h2>Understand your data</h2><div class="coverage-grid">{coverage}</div>{'<ul>'+errors+'</ul>' if errors else ''}<details><summary>Coverage, units & interpretation</summary><ul>{limitations}<li>Charts show observed daily values; lines connect adjacent dates only. No missing days are filled.</li><li>Period controls change the summaries, charts and activity log. The latest-week comparison stays fixed.</li><li>This file is a snapshot. Ask Garmin Learning to generate a new dashboard for refreshed data.</li></ul></details></div></section>
<footer class="footer"><span>Garmin Learning · Personal health & training</span><span>Retrieved {esc(report.get('retrieved_at','unknown'))}</span></footer></main>
<script id="report-data" type="application/json">{payload}</script><script>{js}</script></body></html>'''


def save(report, root=None):
    folder = (Path(root) if root else journal.DATA_DIR) / 'reports'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem = f"overview-{report['start_date']}-{report['end_date']}-{uuid.uuid4().hex[:8]}"
    paths = {}
    for ext, content in [('html', render(report)), ('json', json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))]:
        path = folder / (stem + '.' + ext)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        paths[ext] = str(path)
    return {'status': 'saved', 'source': report['source'], 'files': paths, 'snapshot': True, 'published': False}
