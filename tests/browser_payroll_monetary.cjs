// Native Payroll forms plus forged POSTs; disposable review harness only.
const assert = require('node:assert/strict');

module.exports = async function ({base, send, tab, evaluate, navigate, until}) {
  const f = await (await fetch(base + '/__review/it-fixture')).json();
  const snapshot = async () => await (await fetch(base + '/__review/payroll-snapshot')).json();
  const {browserContextId} = await send('Target.createBrowserContext');
  const t = await tab(browserContextId);
  await navigate(t, '/login');
  await evaluate(t, `(() => {
    document.querySelector('[name="username"]').value='review-user';
    document.querySelector('[name="password"]').value='review-password';
    document.querySelector('form').requestSubmit();
  })()`);
  await until(t, `location.pathname==='/dashboard' && document.readyState==='complete'`);
  async function submitForm(values) {
    await evaluate(t, `(() => {
      const form=document.querySelector('main form');
      for (const [key,value] of Object.entries(${JSON.stringify(values)})) form.elements.namedItem(key).value=value;
      // Deliberately bypass browser number-step constraints to test the server.
      form.noValidate=true; form.requestSubmit();
    })()`);
  }
  const comp=`/payroll/compensation/${f.compensation_id}/edit`;
  await navigate(t, comp);
  const before=await snapshot();
  await submitForm({basic_rate:'0.001'});
  await until(t, `document.body.textContent.includes('no more than two decimal places')`);
  assert.deepEqual(await snapshot(),before);
  await submitForm({basic_rate:'1000.01'});
  await until(t, `location.pathname==='/payroll/compensation' && document.readyState==='complete'`);
  assert.equal((await snapshot()).compensation[0][0],'1000.01');
  assert.equal((await snapshot()).entry[0][1],'1000.00');
  console.log('PASS Chrome compensation overprecision rejection, correction and intentional entry snapshot');

  const period=`/payroll/periods/${f.payroll_period_id}`;
  await navigate(t,period);
  await evaluate(t, `(() => {
    window.confirm=()=>true;
    [...document.querySelectorAll('main form')].find(f=>f.action.endsWith('/calculate-monthly')).requestSubmit();
  })()`);
  await until(t, `document.body.textContent.includes('calculated') && document.readyState==='complete'`);
  let state=await snapshot();
  assert.equal(state.entry[0][0],'CALCULATED'); assert.equal(state.entry[0][4],'500.00');
  assert.equal(state.entry[0][5].length,64);

  const entry=`/payroll/entries/${f.payroll_entry_id}`;
  await navigate(t,entry);
  async function post(amount,token=true) {
    return evaluate(t, `(async()=>{
      const body=new URLSearchParams({adjustment_type:'EARNING',adjustment_name:'Browser earning',amount:${JSON.stringify(amount)}});
      if (${token}) body.set('csrf_token',document.querySelector('meta[name="csrf-token"]').content);
      const r=await fetch(${JSON.stringify(entry+'/adjustments/add')},{method:'POST',body});
      return {status:r.status,text:await r.text()};
    })()`);
  }
  state=await snapshot();
  assert.equal((await post('1.00',false)).status,400);
  assert((await post('NaN')).text.includes('valid finite decimal'));
  assert((await post('9999999999.99')).text.includes('Gross pay must not exceed'));
  assert.deepEqual(await snapshot(),state);
  const valid=await post('0.01'); assert.equal(valid.status,200);
  state=await snapshot(); assert.equal(state.adjustments.length,1);
  assert.equal(state.entry[0][0],'DRAFT'); assert.equal(state.entry[0][4],'500.01');
  assert.equal(state.entry[0][5],null);
  assert.deepEqual(state.audits,before.audits);
  console.log('PASS Chrome Payroll calculation evidence, CSRF, nonfinite/overflow rejection, valid adjustment and evidence invalidation');
};
