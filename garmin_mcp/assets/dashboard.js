'use strict';
(() => {
const report=JSON.parse(document.getElementById('report-data').textContent);
const labels={sleep_hours:['Sleep duration','hours'],hrv_ms:['Overnight HRV','ms'],resting_heart_rate:['Resting heart rate','bpm'],steps:['Daily steps','steps'],sleep_score:['Sleep score','/100'],stress:['Stress','/100'],body_battery_max:['Body Battery peak','/100']};
const dayMs=86400000, parse=s=>new Date(s+'T00:00:00Z'), iso=d=>d.toISOString().slice(0,10), end=parse(report.end_date);
let span=0, metric='sleep_hours';
const $=id=>document.getElementById(id), clean=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
const pretty=(n,d=1)=>num(n)?n.toLocaleString('en-US',{maximumFractionDigits:d}):'—';
const duration=h=>num(h)?`${Math.floor(Math.round(h*60)/60)}h ${Math.round(h*60)%60}m`:'—';
const short=s=>parse(s).toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'});
const mean=a=>a.length?a.reduce((a,b)=>a+b,0)/a.length:null;
function start(){return span?iso(new Date(Math.max(parse(report.start_date),end-(span-1)*dayMs))):report.start_date}
function points(key,from=start(),until=report.end_date){return (report.metrics[key]?.series||[]).filter(p=>p.date>=from&&p.date<=until&&num(p.value))}
function acts(){return report.activities.data.filter(a=>String(a.startTimeLocal||'').slice(0,10)>=start()&&String(a.startTimeLocal||'').slice(0,10)<=report.end_date)}
function sport(a){return a.activityType?.typeKey||'unknown'}
function displaySport(s){return s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}
function stat(id,value,foot){$(id).innerHTML=value;$(id+'-foot').textContent=foot}
function updateStats(){const days=Math.round((end-parse(start()))/dayMs)+1, a=acts(), values=points('sleep_hours');
stat('sleep-value',duration(mean(values.map(p=>p.value))),`${values.length} of ${days} nights recorded`);
const minutes=a.filter(a=>num(a.duration)).reduce((n,a)=>n+a.duration/60,0);
stat('training-value',duration(a.some(a=>num(a.duration))?minutes/60:null),`${a.length} recorded sessions${report.activities.complete?'':' · partial retrieval'}`);
for(const [key,id,unit] of [['hrv_ms','hrv-value','ms'],['resting_heart_rate','heart-value','bpm']]){const p=points(key);stat(id,`${pretty(mean(p.map(x=>x.value)))} <small>${unit}</small>`,`${p.length} of ${days} days recorded`)}
$('selected-dates').textContent=`${short(start())} – ${short(report.end_date)}, ${end.getUTCFullYear()}`;
}
function draw(){const pts=points(metric), first=parse(start()),days=Math.round((end-first)/dayMs)+1;
const width=800,left=48,right=20,plot=width-left-right,top=30,bottom=220,barTop=285,barBottom=345;
const valueList=pts.map(p=>p.value);let lo=Math.min(...valueList),hi=Math.max(...valueList);
if(!pts.length){lo=0;hi=1}else {const padding=Math.max((hi-lo)*.18,metric==='steps'?500:1);lo=Math.max(0,lo-padding);hi+=padding}
const x=d=>left+((parse(d)-first)/dayMs+.5)*plot/days, y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top);
let svg=`<svg viewBox="0 0 ${width} 390" role="img" aria-label="${clean(labels[metric][0])} and recorded training duration over time"><title>${clean(labels[metric][0])} and recorded training minutes, separate scales</title>`;
for(let i=0;i<4;i++){const v=lo+(hi-lo)*i/3,yy=y(v);svg+=`<line x1="${left}" x2="${width-right}" y1="${yy}" y2="${yy}" stroke="#e8edf5"/><text x="${left-10}" y="${yy+4}" text-anchor="end">${pretty(v,metric==='steps'?0:1)}</text>`}
svg+=`<text x="${left}" y="14">${clean(labels[metric][1])}</text>`;
let path='',prev=null;
for(const p of pts){const contiguous=prev&&(parse(p.date)-parse(prev.date)===dayMs);path+=`${contiguous?'L':'M'}${x(p.date).toFixed(2)},${y(p.value).toFixed(2)} `;prev=p}
svg+=`<path d="${path}" fill="none" stroke="#3066db" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
for(const p of pts)svg+=`<circle class="point" cx="${x(p.date)}" cy="${y(p.value)}" r="3.5" fill="#3066db" stroke="white" stroke-width="1.5"><title>${clean(p.date)}: ${pretty(p.value)} ${clean(labels[metric][1])}</title></circle>`;
if(!pts.length)svg+=`<text x="400" y="125" text-anchor="middle">No observations for this metric in the selected period</text>`;
svg+=`<text x="${left}" y="266">Recorded training · minutes</text>`;
const totals={};for(const a of acts()){if(num(a.duration)){const d=a.startTimeLocal.slice(0,10);totals[d]=(totals[d]||0)+a.duration/60}}
const max=Math.max(1,...Object.values(totals));const bw=Math.min(28,plot/days*.6);
for(const [d,v] of Object.entries(totals)){const h=v/max*(barBottom-barTop);svg+=`<rect x="${x(d)-bw/2}" y="${barBottom-h}" width="${bw}" height="${h}" rx="3" fill="#d66b30"><title>${clean(d)}: ${pretty(v)} recorded minutes</title></rect>`}
svg+=`<text x="${left-10}" y="${barTop+4}" text-anchor="end">${pretty(max,0)}</text><text x="${left-10}" y="${barBottom+4}" text-anchor="end">0</text><line x1="${left}" x2="${width-right}" y1="${barBottom}" y2="${barBottom}" stroke="#e3e8f0"/>`;
const every=Math.max(1,Math.ceil(days/6));for(let i=0;i<days;i+=every){const d=iso(new Date(+first+i*dayMs));svg+=`<text x="${x(d)}" y="376" text-anchor="middle">${clean(short(d))}</text>`}
$('timeline').innerHTML=svg+'</svg>';$('metric-legend').textContent=labels[metric][0];$('chart-coverage').textContent=`${pts.length}/${days} days observed`;
}
function comparison(){const recent=iso(new Date(end-6*dayMs)),prior=iso(new Date(end-13*dayMs)),priorEnd=iso(new Date(end-7*dayMs));$('comparison-dates').textContent=`${short(recent)}–${short(report.end_date)} vs ${short(prior)}–${short(priorEnd)}`;
$('comparisons').innerHTML=['sleep_hours','hrv_ms','resting_heart_rate'].map(k=>{const r=points(k,recent).map(p=>p.value),p=points(k,prior,priorEnd).map(p=>p.value),diff=r.length&&p.length?mean(r)-mean(p):null;return `<div class="comparison"><div class="comparison-title">${labels[k][0]}</div><strong>${diff===null?'—':`${diff>0?'+':''}${diff.toFixed(1)}`} <small>${labels[k][1]}</small></strong><p>${diff===null?'Not enough observations to compare':`${pretty(mean(p))} → ${pretty(mean(r))}`}<br>${p.length}/7 prior days · ${r.length}/7 recent days</p></div>`}).join('');
}
function summaries(){const grouped={};for(const a of acts()){const key=sport(a);if(!grouped[key])grouped[key]={count:0,seconds:0,known:0};grouped[key].count++;if(num(a.duration)){grouped[key].seconds+=a.duration;grouped[key].known++}}
const all=Object.entries(grouped).sort((a,b)=>b[1].seconds-a[1].seconds),max=Math.max(1,...all.map(x=>x[1].seconds));
$('sports').innerHTML=all.map(([s,v])=>`<div class="sport-row"><span>${clean(displaySport(s))}<br><small>${v.count} sessions</small></span><div class="sport-track"><div class="sport-fill" style="width:${v.seconds/max*100}%"></div></div><span class="sport-time">${v.known?pretty(v.seconds/60,0)+' min':'—'}${v.known<v.count?'*':''}</span></div>`).join('')||'<p class="empty">No recorded activities in this period.</p>';
$('more-metrics').innerHTML=['steps','sleep_score','stress','body_battery_max'].map(k=>{const p=points(k);return `<div class="detail-metric"><p>${labels[k][0]}</p><strong>${pretty(mean(p.map(x=>x.value)),k==='steps'?0:1)} <small>${labels[k][1]}</small></strong><small>${p.length} days observed</small></div>`}).join('');
}
function table(){const selected=$('sport-filter').value,a=acts().filter(a=>!selected||sport(a)===selected).sort((a,b)=>String(b.startTimeLocal).localeCompare(String(a.startTimeLocal)));
$('activity-count').textContent=`${a.length} sessions shown`;
$('activity-rows').innerHTML=a.map(a=>`<tr><td>${clean(short(a.startTimeLocal.slice(0,10)))}<br><small>${clean(a.startTimeLocal.slice(11,16))}</small></td><td class="title">${clean(a.activityName||displaySport(sport(a)))}<small>${clean(displaySport(sport(a)))}</small></td><td>${num(a.duration)?pretty(a.duration/60)+' min':'—'}</td><td>${num(a.distance)&&/running|cycling|swimming|walking/.test(sport(a))?pretty(a.distance/1000,2)+' km':'—'}</td><td>${pretty(a.averageHR,0)}${num(a.averageHR)?' bpm':''}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No activities match this selection. Try another sport or a longer period.</td></tr>';
}
function update(){updateStats();draw();summaries();table()}
document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{span=Number(b.dataset.range);document.querySelectorAll('[data-range]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));update()}));
document.querySelectorAll('[data-metric]').forEach(b=>b.addEventListener('click',()=>{metric=b.dataset.metric;document.querySelectorAll('[data-metric]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));draw()}));
$('sport-filter').innerHTML='<option value="">All sports</option>'+[...new Set(report.activities.data.map(sport))].sort().map(s=>`<option value="${clean(s)}">${clean(displaySport(s))}</option>`).join('');$('sport-filter').addEventListener('change',table);comparison();update();
})();
