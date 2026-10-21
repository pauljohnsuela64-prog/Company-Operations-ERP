// Native Supplier checks against the verified disposable security-review instance.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/procurement/suppliers?search=SUP-HISTORY&status=inactive&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1-25 of 121 suppliers | Page 1 of 5')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'SUP-HISTORY',status:'inactive',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  for(const size of [50,100]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),size);
  }
  await navigate(manager,filters.replace('page_size=25','page_size=100')+'&page=999');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),21);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('SUP-HISTORY-0120')`),true);
  await navigate(manager,'/procurement/suppliers?search=ITEM%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No suppliers match these filters.')`),true);
  const invalid=await evaluate(manager,`(async()=>{const results=[];for(const q of ['status=bad','page_size=500','search=x&search=y']){const r=await fetch('/procurement/suppliers?'+q);results.push([r.status,(await r.text()).includes('Suppliers were not loaded.')]);}return results;})()`);
  for(const result of invalid)assert.deepEqual(result,[400,true]);
  const data={supplier_code:'SUP-BROWSER',supplier_name:'PRIVATE supplier name',contact_person:'PRIVATE contact',email:'private@example.test',phone:'PRIVATE phone',address:'PRIVATE <img src=x onerror=alert(1)>'};
  async function submit(values,forged=false){
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(key).value=value;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  await navigate(manager,'/procurement/suppliers/add');await submit({...data,address:'x'.repeat(256)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('255 characters')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="address"]').value.length`),256);
  assert.equal(await evaluate(manager,`document.querySelector('[name="supplier_name"]').value`),data.supplier_name);
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await submit(data);await until(manager,`location.pathname==='/procurement/suppliers' && document.readyState==='complete'`);
  await navigate(manager,'/procurement/suppliers/add');await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('already exists')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="address"]').value`),data.address);
  await navigate(manager,'/procurement/suppliers?search=SUP-BROWSER');
  const edit=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
  await navigate(manager,edit);await submit(data);
  await until(manager,`location.pathname==='/procurement/suppliers' && document.body.textContent.includes('No supplier changes were needed.')`);
  await navigate(manager,edit);await submit({...data,supplier_name:'PRIVATE revised supplier'});
  await until(manager,`location.pathname==='/procurement/suppliers' && document.readyState==='complete'`);
  await navigate(manager,'/procurement/suppliers?search=SUP-BROWSER');
  const status=edit.replace('/edit','/status');
  for(const target of ['0','0','1']){
    const result=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'${target}',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return [r.status,new URL(r.url).pathname];})()`);
    assert.deepEqual(result,[200,'/procurement/suppliers']);
  }
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  // Native optional fields remain optional; do not add a contact/email policy.
  await navigate(manager,'/procurement/suppliers/add');
  await submit({supplier_code:'SUP-OPTIONAL',supplier_name:'Optional fields'});
  await until(manager,`location.pathname==='/procurement/suppliers' && document.readyState==='complete'`);
  const viewer=await login('denied-user');await navigate(viewer,'/procurement/suppliers?search=SUP-BROWSER');
  assert.equal(await evaluate(viewer,`document.querySelectorAll('main a[href$="/edit"],main form[method="POST"],main a[href$="/add"]').length`),0);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome Suppliers 25/50/100 pages, preserved filters/counts, literal/invalid filters, escaped retained values, duplicate/no-op edits, explicit status replay, permissions and CSRF');
};
