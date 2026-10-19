// Native generation forms; synthetic activated policy from the preceding review.
const assert = require('node:assert/strict');
module.exports = async function({base,send,tab,evaluate,navigate,until}) {
  const snapshot=async()=>await(await fetch(base+'/__review/generation-snapshot')).json();
  async function login(name) {
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{document.querySelector('[name="username"]').value=${JSON.stringify(name)};
      document.querySelector('[name="password"]').value='review-password';document.querySelector('form').requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const t=await login('review-user');await navigate(t,'/payroll/periods/generate');
  async function submit(values,action) {
    await evaluate(t,`(()=>{const f=document.querySelector('main form');f.noValidate=true;
      for(const [k,v]of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(k).value=v;
      f.requestSubmit(f.querySelector('button[value="${action}"]'));})()`);
  }
  const before=await snapshot();
  await submit({year:'2040',month:'2'},'preview');
  await until(t,`document.body.textContent.includes('Preview only')`);
  assert(await evaluate(t,`document.body.textContent.includes('2040-02-29')`));
  assert.deepEqual(await snapshot(),before);
  await submit({pay_date_a:'2040-02-14',pay_date_b:'2040-02-29'},'generate');
  await until(t,`document.body.textContent.includes('on or after the cutoff end')`);
  assert.equal(await evaluate(t,`document.querySelector('[name="pay_date_a"]').value`),'2040-02-14');
  assert.deepEqual(await snapshot(),before);
  await submit({pay_date_a:'2040-02-15'},'generate');
  await until(t,`document.body.textContent.includes('Generation complete.')`);
  const generated=await snapshot();assert.equal(generated.periods.length,2);
  assert.equal(generated.audits.length,before.audits.length+2);
  assert(generated.audits.slice(-2).every(row=>row[0]===1&&row[1]==='CREATE'));
  await submit({},'generate');await until(t,`document.body.textContent.includes('Both matching periods already exist')`);
  assert.deepEqual(await snapshot(),generated);
  await submit({pay_date_a:'2040-02-16'},'generate');await until(t,`document.body.textContent.includes('conflicts with an existing period')`);
  assert.deepEqual(await snapshot(),generated);
  const status=await evaluate(t,`(async()=>{const r=await fetch('/payroll/periods/generate',{method:'POST',body:new URLSearchParams({action:'generate'})});return r.status;})()`);
  assert.equal(status,400);assert.deepEqual(await snapshot(),generated);
  const viewer=await login('policy-viewer');await navigate(viewer,'/payroll/periods');
  assert(!(await evaluate(viewer,`document.body.textContent.includes('Generate Monthly Cutoffs')`)));
  await evaluate(viewer,`location.href='/payroll/periods/generate'`);await until(viewer,`location.pathname==='/dashboard' && document.readyState==='complete'`);
  assert.deepEqual(await snapshot(),generated);
  console.log('PASS Chrome native cutoff preview, leap February, explicit-date retention/correction, generation, audit actors, duplicate/conflict rejection, viewer controls and CSRF');
};
