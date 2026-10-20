// Native Attendance forms on the verified disposable security-review server.
const assert = require('node:assert/strict');
module.exports = async ({send,tab,evaluate,navigate,until,fixture}) => {
  async function login(username) {
    const {browserContextId}=await send('Target.createBrowserContext');
    const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(() => { const f=document.querySelector('form'); f.username.value=${JSON.stringify(username)}; f.password.value='review-password'; f.requestSubmit(); })()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);
    return t;
  }
  const manager=await login('review-user');
  const filters='/attendance?search=ATT-BROWSER&status=PRESENT&department_id='+fixture.department+'&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('61 records')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const url=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'ATT-BROWSER',status:'PRESENT',department_id:String(fixture.department),page_size:'25',page:'2'})) assert.equal(url.searchParams.get(key),value);
  await navigate(manager,next);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Page 2 of 3')`),true);
  for(const [size,count] of [[50,50],[100,61]]) {
    await evaluate(manager,`(() => { const s=document.querySelector('[name="page_size"]'); s.value='${size}'; s.form.requestSubmit(); })()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),count);
  }
  await navigate(manager,'/attendance?search=ATT%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No attendance records match')`),true);
  console.log('PASS Chrome Attendance 25/50/100 pages, complete filtered totals, preserved filters and literal wildcard search');
  async function submit(values,forged=false) {
    await evaluate(manager,`(() => { const f=document.querySelector('main form'); for(const [key,value] of Object.entries(${JSON.stringify(values)})) { const el=f.elements.namedItem(key); if(el.tagName==='SELECT' && ![...el.options].some(o=>o.value===value)) el.add(new Option('Synthetic forged reference',value)); el.value=value; } ${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'}; })()`);
  }
  const data={employee_id:String(fixture.employee),attendance_date:'2026-03-01',time_in:'08:01:02',time_out:'17:02:03',status:'PRESENT',notes:'PRIVATE <img src=x onerror=alert(1)> & notes'};
  await navigate(manager,'/attendance/add');
  await submit({...data,notes:'X'.repeat(256)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Notes must not exceed 255 characters.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="notes"]').value`),'X'.repeat(256));
  assert.equal(await evaluate(manager,`document.querySelector('[name="employee_id"]').value`),data.employee_id);
  await submit(data);
  await until(manager,`location.pathname==='/attendance' && document.readyState==='complete'`);
  await navigate(manager,'/attendance?search=ATT-BROWSER&date=2026-03-01');
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  const edit=await evaluate(manager,`document.querySelector('main a[href$="/edit"]').getAttribute('href')`);
  await navigate(manager,'/attendance/add');
  await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('already has an attendance record')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="notes"]').value`),data.notes);
  await navigate(manager,edit);
  assert.equal(await evaluate(manager,`document.querySelector('[name="time_in"]').value`),'08:01:02');
  await submit({...data,employee_id:'999999'},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Employee not found.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="notes"]').value`),data.notes);
  await submit({...data,status:'HALF_DAY',time_in:'23:59:59',time_out:'00:00:00'});
  await until(manager,`location.pathname==='/attendance' && document.readyState==='complete'`);
  assert.equal(await evaluate(manager,`document.querySelector('main tbody tr').textContent.includes('00:00:00')`),true);
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(edit)},{method:'POST',body:new URLSearchParams({employee_id:'${fixture.employee}',attendance_date:'2026-03-01',status:'ABSENT',csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  const viewer=await login('attendance-viewer');
  await navigate(viewer,filters);
  assert.equal(await evaluate(viewer,`document.querySelector('main a[href="/attendance/add"]')===null`),true);
  assert.equal(await evaluate(viewer,`document.querySelector('main a[href$="/edit"]')===null`),true);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch('/attendance/add',{method:'POST',body:new URLSearchParams({employee_id:'${fixture.employee}',attendance_date:'2026-03-02',status:'PRESENT',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome Attendance retained/escaped validation feedback, duplicate rejection, second-precision editing, manual statuses, CSRF and viewer denial');
};
