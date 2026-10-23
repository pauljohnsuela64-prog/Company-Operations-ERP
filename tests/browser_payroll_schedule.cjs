// Payroll scheduling correction on the synthetic security-review server only.
const assert = require('node:assert/strict');
module.exports = async ({send, tab, evaluate, navigate, until}) => {
  async function login(username) {
    const {browserContextId} = await send('Target.createBrowserContext');
    const t = await tab(browserContextId);
    await navigate(t, '/login');
    await evaluate(t, "(()=>{const f=document.querySelector('form');f.username.value="+JSON.stringify(username)+";f.password.value='review-password';f.requestSubmit();})()");
    await until(t, "location.pathname==='/dashboard' && document.readyState==='complete'");
    return t;
  }
  const manager = await login('review-user');
  const values = {period_name:'Browser late conflict <safe>',start_date:'2027-02-01',end_date:'2027-02-15',pay_date:'2027-02-16',notes:'Retained browser notes'};
  async function submit(t, values) {
    await evaluate(t, "(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries("+JSON.stringify(values)+"))f.elements.namedItem(key).value=value;f.requestSubmit();})()");
  }
  await navigate(manager, '/payroll/periods/add');
  await submit(manager, values);
  await until(manager, "document.readyState==='complete' && document.body.textContent.includes('overlaps another active period')");
  for (const [name, value] of Object.entries(values)) {
    assert.equal(await evaluate(manager, 'document.getElementsByName('+JSON.stringify(name)+')[0].value'), value);
  }
  assert.equal(await evaluate(manager, "document.querySelector('main safe')===null"), true);
  assert.equal(await evaluate(manager, "document.getElementsByName('csrf_token').length>0"), true);
  await submit(manager, {...values,period_name:'Browser valid schedule',start_date:'2027-03-01',end_date:'2027-03-15',pay_date:'2027-03-16'});
  await until(manager, "location.pathname==='/payroll/periods' && document.readyState==='complete'");
  const view = await evaluate(manager, "[...document.querySelectorAll('main tbody tr')].find(r=>r.textContent.includes('Browser valid schedule')).querySelector('a').getAttribute('href')");
  const edit = view + '/edit';
  await navigate(manager, edit);
  await submit(manager, {...values,period_name:'Browser late edit <safe>',start_date:'2027-04-01',end_date:'2027-04-15',pay_date:'2027-04-16'});
  await until(manager, "document.readyState==='complete' && document.body.textContent.includes('overlaps another active period')");
  assert.equal(await evaluate(manager, "document.getElementsByName('period_name')[0].value"), 'Browser late edit <safe>');
  assert.equal(await evaluate(manager, "document.getElementsByName('start_date')[0].value"), '2027-04-01');
  await submit(manager, {...values,period_name:'Browser valid revised',start_date:'2027-05-01',end_date:'2027-05-15',pay_date:'2027-05-16'});
  await until(manager, "location.pathname==='/payroll/periods' && document.readyState==='complete'");
  const reader = await login('denied-user');
  await navigate(reader, '/payroll/periods');
  assert.equal(await evaluate(reader, "[...document.querySelectorAll('main a')].some(a=>a.pathname==='/payroll/periods/add')"), false);
  const denied = await evaluate(reader, "(async()=>{const r=await fetch('/payroll/periods/add',{method:'POST',body:new URLSearchParams({..."+JSON.stringify(values)+",csrf_token:document.querySelector('meta[name=csrf-token]').content})});return new URL(r.url).pathname;})()");
  assert.equal(denied, '/dashboard');
  console.log('PASS Chrome Payroll late create/edit conflicts retain escaped values and CSRF; corrected native saves persist; reader cannot write');
};
