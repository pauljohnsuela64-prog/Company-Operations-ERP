// All records/users live only in mysql_security_review's disposable server.
const assert=require('node:assert/strict');
module.exports=async function({base,controlKey,send,tab,evaluate,navigate,until}) {
  const snapshot=async()=>await(await fetch(base+'/__review/policy-snapshot')).json();
  async function login(username) {
    const {browserContextId}=await send('Target.createBrowserContext');
    const t=await tab(browserContextId);await navigate(t,'/login');
    await evaluate(t,`(()=>{document.querySelector('[name="username"]').value=${JSON.stringify(username)};
      document.querySelector('[name="password"]').value='review-password';document.querySelector('form').requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  async function form(t,values) {
    await evaluate(t,`(()=>{const f=document.querySelector('main form');f.noValidate=true;
      for(const [name,value]of Object.entries(${JSON.stringify(values)})) {
        const e=f.elements.namedItem(name); if(e.type==='checkbox')e.checked=!!value;else e.value=value;
      } f.requestSubmit();})()`);
  }
  async function post(t,path,fields={},token=true,headers={}) {
    return evaluate(t,`(async()=>{const body=new URLSearchParams(${JSON.stringify(fields)});
      if(${token})body.set('csrf_token',document.querySelector('meta[name="csrf-token"]').content);
      const r=await fetch(${JSON.stringify(path)},{method:'POST',body,headers:${JSON.stringify(headers)}});
      return {status:r.status,path:new URL(r.url).pathname,text:await r.text()};})()`);
  }
  const manager=await login('policy-manager');
  await navigate(manager,'/payroll/policies/add');const before=await snapshot();
  await form(manager,{policy_name:'x'.repeat(101),effective_from:'2040-01-01'});
  await until(manager,`document.body.textContent.includes('must not exceed 100')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="policy_name"]').value`),'x'.repeat(101));
  assert.deepEqual(await snapshot(),before);
  await form(manager,{policy_name:'Browser synthetic policy',effective_from:'2040-01-01'});
  await until(manager,"location.pathname.startsWith('/payroll/policies/') && Number(location.pathname.split('/').pop())>0 && document.readyState==='complete'");
  const path=await evaluate(manager,'location.pathname');const id=Number(path.split('/').pop());
  const viewer=await login('policy-viewer');await navigate(viewer,path);
  assert(!(await evaluate(viewer,`document.body.textContent.includes('Edit Draft') || !!document.querySelector('main form')`)));
  const saved=await snapshot();
  for(const endpoint of ['/payroll/policies/add',path+'/edit',path+'/approve',path+'/activate']) {
    assert.equal((await post(viewer,endpoint)).path,'/dashboard');
  }
  assert.deepEqual(await snapshot(),saved);
  const stale=await login('policy-manager'); // Independent stale form for the same actor.
  await navigate(manager,path+'/edit');await navigate(stale,path+'/edit');
  await form(manager,{policy_name:'Browser first edit'});
  await until(manager,`location.pathname===${JSON.stringify(path)} && document.readyState==='complete'`);
  const edited=await snapshot();
  await form(stale,{policy_name:'Browser stale edit'});
  await until(stale,`document.body.textContent.includes('draft changed')`);
  assert.equal(await evaluate(stale,`document.querySelector('[name="policy_name"]').value`),'Browser stale edit');
  assert.deepEqual(await snapshot(),edited);
  await navigate(manager,path+'/edit');
  await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const e of f.querySelectorAll('select')) {
    e.value=[...e.options].some(o=>o.value==='BLOCK')?'BLOCK':'VERIFIED_FULL_CUTOFF_ONLY';
  } f.requestSubmit();})()`);
  await until(manager,`location.pathname===${JSON.stringify(path)} && document.readyState==='complete'`);
  const approver=await login('policy-approver');await navigate(approver,path);
  assert(!(await evaluate(approver,`document.body.textContent.includes('Edit Draft')`)));
  const resolved=await snapshot();
  assert.equal((await post(approver,path+'/approve',{revision:'3',approval_reference:'HR-BROWSER-001',confirm_approval:'yes'},false)).status,400);
  assert.deepEqual(await snapshot(),resolved);
  await form(approver,{approval_reference:'pending',confirm_approval:true});
  await until(approver,`document.body.textContent.includes('meaningful reference')`);
  assert.equal(await evaluate(approver,`document.querySelector('[name="approval_reference"]').value`),'pending');
  await form(approver,{approval_reference:'Synthetic HR/Finance BROWSER-001',confirm_approval:true});
  await until(approver,`document.body.textContent.includes('approved and sealed')`);
  const activator=await login('policy-activator');await navigate(activator,path);
  assert(await evaluate(activator,`document.body.textContent.includes('Schedule Activation')`));
  await form(activator,{confirm_activation:true});
  await until(activator,`document.body.textContent.includes('Policy activation scheduled')`);
  let state=await snapshot();
  assert.equal(state.activations.length,1);
  const events=state.audits.filter(e=>Number(e[2])===id);
  assert.deepEqual(events.map(e=>[e[0],e[1]]),[[8,'CREATE'],[8,'UPDATE'],[8,'UPDATE'],[9,'APPROVE'],[10,'ACTIVATE']]);
  const scheduled=await snapshot();await post(activator,path+'/activate',{confirm_activation:'yes'});
  assert.deepEqual(await snapshot(),scheduled);
  assert(await evaluate(activator,`document.body.textContent.includes('Asia/Manila')`));
  await navigate(manager,'/payroll/policies/add');
  assert.equal((await post(manager,'/__review/policy-control',{action:'revoke_manage'},true,{'X-Review-Key':controlKey})).status,200);
  await form(manager,{policy_name:'Denied after revocation',effective_from:'2040-02-01'});
  await until(manager,`location.pathname==='/dashboard' && document.readyState==='complete'`);
  assert.deepEqual(await snapshot(),scheduled);
  assert.equal((await post(activator,'/__review/policy-control',{action:'disable_activate'},true,{'X-Review-Key':controlKey})).status,200);
  assert.equal((await post(activator,path+'/activate',{confirm_activation:'yes'})).path,'/login');
  assert.deepEqual(await snapshot(),scheduled);
  console.log('PASS Chrome policy roles/native forms, retained validation/stale edits, approval/hash/activation actors, forged POST/CSRF, duplicate rejection, revocation and disabled account');
};
