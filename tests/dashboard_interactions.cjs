// Pure JavaScript unit harness: no browser, network or UI automation.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function mount(report){
  const elements=new Map();
  function element(id,dataset={}){return {id,dataset,innerHTML:'',textContent:'',value:'',listeners:{},attributes:{},addEventListener(k,f){this.listeners[k]=f},setAttribute(k,v){this.attributes[k]=v}}}
  const ranges=[0,14,7].map(n=>element('',{range:String(n)}));
  const metrics=['sleep_hours','hrv_ms','resting_heart_rate','steps'].map(k=>element('',{metric:k}));
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element(id));return elements.get(id)},querySelectorAll(selector){return selector==='[data-range]'?ranges:metrics}};
  document.getElementById('report-data').textContent=JSON.stringify(report);
  vm.runInNewContext(fs.readFileSync('garmin_mcp/assets/dashboard.js','utf8'),{document});
  return {elements,ranges,metrics};
}
const dates=Array.from({length:22},(_,i)=>`2026-10-${String(i+1).padStart(2,'0')}`);
const report={start_date:dates[0],end_date:dates.at(-1),metrics:{},activities:{complete:true,data:[]}};
for(const k of ['sleep_hours','hrv_ms','resting_heart_rate','steps','sleep_score','stress','body_battery_max']){
 report.metrics[k]={series:dates.map((date,i)=>({date,value:k==='sleep_hours'?7:i+1}))};
}
report.activities.data=dates.map((d,i)=>({startTimeLocal:d+' 08:00:00',activityName:i===0?'<img src=x onerror=alert(1)>':'Run',duration:1800,distance:5000,averageHR:140,activityType:{typeKey:i%2?'cycling':'running'}}));
let m=mount(report);
assert.equal(m.elements.get('sleep-value').innerHTML,'7h 0m');
assert.equal(m.elements.get('training-value').innerHTML,'11h 0m');
assert.equal(m.elements.get('activity-count').textContent,'22 sessions shown');
assert.ok(!m.elements.get('activity-rows').innerHTML.includes('<img'));
assert.ok(m.elements.get('activity-rows').innerHTML.includes('&lt;img'));
const comparison=m.elements.get('comparisons').innerHTML;
m.ranges[2].listeners.click();
assert.equal(m.elements.get('activity-count').textContent,'7 sessions shown');
assert.equal(m.elements.get('training-value').innerHTML,'3h 30m');
assert.equal(m.elements.get('chart-coverage').textContent,'7/7 days observed');
assert.equal(m.elements.get('comparisons').innerHTML,comparison);
m.elements.get('sport-filter').value='running';m.elements.get('sport-filter').listeners.change();
assert.equal(m.elements.get('activity-count').textContent,'3 sessions shown');
m.metrics[1].listeners.click();
assert.equal(m.elements.get('metric-legend').textContent,'Overnight HRV');
assert.ok(m.elements.get('timeline').innerHTML.includes('aria-label="Overnight HRV'));
report.metrics.hrv_ms.series=report.metrics.hrv_ms.series.filter(p=>p.date!=='2026-10-16');
m=mount(report);m.metrics[1].listeners.click();
assert.equal(m.elements.get('chart-coverage').textContent,'21/22 days observed');
const line=m.elements.get('timeline').innerHTML.match(/<path d="([^"]*)"/)[1];
assert.equal((line.match(/M/g)||[]).length,2,'missing day must break the line');
for(const metric of Object.values(report.metrics))metric.series=[];
report.activities.data=[];
m=mount(report);
assert.equal(m.elements.get('sleep-value').innerHTML,'—');
assert.equal(m.elements.get('training-value').innerHTML,'—');
assert.ok(!/NaN|Infinity/.test(m.elements.get('timeline').innerHTML));
assert.ok(m.elements.get('activity-rows').innerHTML.includes('No activities match'));
console.log('Dashboard behavior checks passed: ranges, metrics, sport filter, fixed comparison, missing-day gaps, escaping and empty states.');
