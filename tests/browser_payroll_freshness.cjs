// Actual native forms on the synthetic security-review instance.
const assert = require('node:assert/strict');
module.exports = async ({send, tab, evaluate, navigate, until, fixture, dialogs, errors}) => {
  async function login(username) {
    const {browserContextId} = await send('Target.createBrowserContext');
    const t = await tab(browserContextId);
    await navigate(t, '/login');
    await evaluate(t, "(()=>{const f=document.querySelector('form');f.username.value="+JSON.stringify(username)+";f.password.value='review-password';f.requestSubmit();})()");
    await until(t, "location.pathname==='/dashboard' && document.readyState==='complete'");
    return t;
  }
  const manager = await login('review-user');
  const approver = await login('freshness-approver');
  const reader = await login('denied-user');
  async function action(t, period, suffix, expected) {
    await navigate(t, '/payroll/periods/'+period);
    await evaluate(t, "(()=>{const form=[...document.querySelectorAll('main form')].find(f=>new URL(f.action).pathname.endsWith("+JSON.stringify('/'+suffix)+"));if(!form)throw Error('Missing action form');form.requestSubmit();})()");
    await until(t, "document.readyState==='complete' && document.body.textContent.includes("+JSON.stringify(expected)+")");
  }
  async function attendance(status) {
    await navigate(manager, '/attendance/'+fixture.attendance+'/edit');
    await evaluate(manager, "(()=>{const f=document.querySelector('main form');f.elements.namedItem('status').value="+JSON.stringify(status)+";f.requestSubmit();})()");
    await until(manager, "location.pathname==='/attendance' && document.readyState==='complete'");
  }
  await attendance('ABSENT');
  await action(manager,fixture.stale,'submit','Attendance changed after Payroll calculation');
  await action(manager,fixture.stale,'calculate-monthly','payroll entries calculated');
  await action(manager,fixture.stale,'submit','submitted for approval');
  await attendance('PRESENT');
  await action(approver,fixture.stale,'approve','Attendance changed after Payroll calculation');
  await action(manager,fixture.stale,'return-to-draft','returned to Draft');
  await action(manager,fixture.stale,'calculate-monthly','payroll entries calculated');
  await action(manager,fixture.stale,'submit','submitted for approval');
  await action(approver,fixture.stale,'approve','approved successfully');
  await attendance('ABSENT');
  await action(approver,fixture.stale,'paid','Payment blocked.');
  assert.equal(await evaluate(approver,"document.body.textContent.includes('APPROVED Payroll was not reopened')"),true);
  await action(approver,fixture.legacy,'paid','unverified');
  await action(manager,fixture.valid,'submit','submitted for approval');
  await action(approver,fixture.valid,'approve','approved successfully');
  await action(approver,fixture.valid,'paid','marked as paid');
  await navigate(reader,'/payroll/periods/'+fixture.stale);
  assert.equal(await evaluate(reader,"document.querySelectorAll('main form').length"),0);
  const paths = ['/payroll/periods/'+fixture.stale+'/paid','/attendance/'+fixture.attendance+'/edit'];
  for (const path of paths) {
    const status = await evaluate(reader,"(async()=>{const r=await fetch("+JSON.stringify(path)+",{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name=csrf-token]').content})});return new URL(r.url).pathname;})()");
    assert.equal(status,'/dashboard');
  }
  await navigate(manager,'/payroll/periods/'+fixture.stale);
  const csrf = await evaluate(manager,"(async()=>{const r=await fetch('/payroll/periods/"+fixture.stale+"/paid',{method:'POST',body:new URLSearchParams({csrf_token:'invalid'})});return r.status;})()");
  assert.equal(csrf,400);
  assert(dialogs.length>=8, 'Native Payroll confirmation dialogs were not exercised');
  assert.deepEqual(errors,[], 'Unexpected JavaScript exceptions');
  console.log('PASS Chrome Payroll freshness: native Attendance edits, stale submit/approve/pay denial, explicit recovery, valid payment, legacy block, reader and CSRF guards');
};
