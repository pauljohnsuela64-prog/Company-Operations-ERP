// Native preparation/review only. No authoritative source adapter is installed.
const assert=require('node:assert/strict');
module.exports=async function({base,send,tab,evaluate,navigate,until}) {
  const state=await(await fetch(base+'/__review/generation-snapshot')).json();
  const period=state.periods[0][0];
  async function login(name) {
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{document.querySelector('[name="username"]').value=${JSON.stringify(name)};document.querySelector('[name="password"]').value='review-password';document.querySelector('form').requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const t=await login('review-user');
  await navigate(t,`/payroll/periods/${period}/certifications/prepare`);
  async function submit(values) {
    await evaluate(t,`(()=>{const f=document.querySelector('main form');f.noValidate=true;
      for(const [k,v]of Object.entries(${JSON.stringify(values)})) {
        const e=f.elements.namedItem(k);if(e.multiple){for(const o of e.options)o.selected=v.includes(o.value);}else e.value=v;
      }f.requestSubmit();})()`);
  }
  await submit({employee_ids:['1'],roster_reference:'pending',calendar_reference:'Synthetic calendar BROWSER-CERT-001'});
  await until(t,`document.body.textContent.includes('meaningful supporting reference')`);
  assert(await evaluate(t,`document.querySelector('[name="employee_ids"]').selectedOptions[0].value==='1'`));
  await submit({roster_reference:'Synthetic authoritative roster BROWSER-CERT-001'});
  await until(t,`location.pathname.startsWith('/payroll/certifications/') && document.body.textContent.includes('MISSING')`);
  const path=await evaluate(t,'location.pathname');
  await navigate(t,path+'/members/1');
  await submit({disposition:'EXCLUDE',eligibility:'UNRESOLVED',verification_status:'VERIFIED',exclusion_reason:'',exclusion_reference:'Synthetic HR BROWSER-CERT-002'});
  await until(t,`document.body.textContent.includes('Exclusion reason')`);
  assert.equal(await evaluate(t,`document.querySelector('[name="exclusion_reference"]').value`),'Synthetic HR BROWSER-CERT-002');
  await submit({exclusion_reason:'Unknown employment history requires separate HR review'});
  await until(t,`location.pathname===${JSON.stringify(path)} && document.readyState==='complete'`);
  assert(await evaluate(t,`document.querySelector('button.btn-success').disabled`));
  assert(await evaluate(t,`document.body.textContent.includes('Publication is unavailable')`));
  const result=await evaluate(t,`(async()=>{const f=document.querySelector('form[action$="/publish"]');const body=new URLSearchParams(new FormData(f));const r=await fetch(f.action,{method:'POST',body});return await r.text();})()`);
  assert(result.includes('Publication is unavailable'));
  const csrf=await evaluate(t,`(async()=>{const r=await fetch(${JSON.stringify(path+'/publish')},{method:'POST',body:new URLSearchParams()});return r.status;})()`);
  assert.equal(csrf,400);
  const viewer=await login('policy-viewer');await navigate(viewer,path);
  assert(!(await evaluate(viewer,`!!document.querySelector('main form') || document.body.textContent.includes('Edit Declared Roster')`)));
  const denied=await evaluate(viewer,`(async()=>{const body=new URLSearchParams({csrf_token:document.querySelector('meta[name="csrf-token"]').content});const r=await fetch(${JSON.stringify(path+'/publish')},{method:'POST',body});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  const after=await(await fetch(base+'/__review/generation-snapshot')).json();assert.deepEqual(after,state);
  console.log('PASS Chrome certification preparation, retained errors/exclusions, reviewed ERP facts, production publication blocker, viewer denial and CSRF; Payroll periods/audits unchanged');
};
