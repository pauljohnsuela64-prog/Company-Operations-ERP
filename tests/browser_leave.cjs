// Native Leave workflow on the verified synthetic security-review server.
const assert = require('node:assert/strict');
module.exports = async ({send,tab,evaluate,navigate,until,fixture}) => {
  async function login(username) {
    const {browserContextId}=await send('Target.createBrowserContext');
    const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(() => {const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);
    return t;
  }
  const manager=await login('review-user');
  const filters='/leave/requests?search=LEAVE-BROWSER&status=REJECTED&leave_type_id='+fixture.type+'&department_id='+fixture.department+'&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('61 requests')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'LEAVE-BROWSER',status:'REJECTED',leave_type_id:String(fixture.type),department_id:String(fixture.department),page_size:'25',page:'2'})) assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Page 2 of 3')`),true);
  for(const [size,count] of [[50,50],[100,61]]) {
    await evaluate(manager,`(() => {const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),count);
  }
  await navigate(manager,'/leave/requests?search=LEAVE%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No leave requests found.')`),true);
  async function submit(values,forged=false) {
    await evaluate(manager,`(() => {const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(key).value=value;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  const data={employee_id:String(fixture.employee),leave_type_id:String(fixture.type),start_date:'2035-01-01',end_date:'2035-01-02',reason:'PRIVATE <img src=x onerror=alert(1)> & leave reason'};
  await navigate(manager,'/leave/requests/add');
  await submit({...data,reason:'X'.repeat(501)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Reason must not exceed 500 characters.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="reason"]').value`),'X'.repeat(501));
  assert.equal(await evaluate(manager,`document.querySelector('[name="employee_id"]').value`),data.employee_id);
  await submit(data);
  await until(manager,`location.pathname.startsWith('/leave/requests/') && /^[0-9]+$/.test(location.pathname.split('/').pop()) && document.readyState==='complete'`);
  const detail=await evaluate(manager,'location.pathname');
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await navigate(manager,'/leave/requests/add');await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('overlaps the selected dates')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="reason"]').value`),data.reason);
  await navigate(manager,detail);
  await evaluate(manager,`document.querySelector('form[action$="/approve"]').requestSubmit()`);
  await until(manager,`document.readyState==='complete' && document.querySelector('form[action$="/approve"]')===null`);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('approved successfully')`),true);
  await navigate(manager,'/leave/requests/add');await submit({...data,start_date:'2035-02-01',end_date:'2035-02-01'});
  await until(manager,`location.pathname.startsWith('/leave/requests/') && /^[0-9]+$/.test(location.pathname.split('/').pop()) && document.readyState==='complete'`);
  await evaluate(manager,`(() => {const f=document.querySelector('form[action$="/reject"]');f.rejection_reason.value='X'.repeat(501);HTMLFormElement.prototype.submit.call(f);})()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Rejection reason must not exceed 500 characters.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="rejection_reason"]').value`),'X'.repeat(501));
  await evaluate(manager,`(() => {const f=document.querySelector('form[action$="/reject"]');f.rejection_reason.value='PRIVATE rejection';f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && document.querySelector('form[action$="/reject"]')===null`);
  await navigate(manager,'/leave/requests/add');await submit({...data,start_date:'2035-03-01',end_date:'2035-03-01'});
  await until(manager,`location.pathname.startsWith('/leave/requests/') && /^[0-9]+$/.test(location.pathname.split('/').pop()) && document.readyState==='complete'`);
  await evaluate(manager,`document.querySelector('form[action$="/cancel"]').requestSubmit()`);
  await until(manager,`document.readyState==='complete' && document.querySelector('form[action$="/cancel"]')===null`);
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(detail+'/approve')},{method:'POST',body:new URLSearchParams({csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  const viewer=await login('leave-viewer');await navigate(viewer,filters);
  assert.equal(await evaluate(viewer,`document.querySelector('main a[href="/leave/requests/add"]')===null`),true);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(detail+'/approve')},{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome Leave 25/50/100 pages, retained filters/counts, literal search, escaped/recoverable validation, overlap conflicts, approve/reject/cancel, CSRF and viewer denial');
};
