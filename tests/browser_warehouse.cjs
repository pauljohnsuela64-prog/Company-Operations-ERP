// Native Warehouse forms on the verified disposable security-review instance.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/inventory/warehouses?search=WH-HISTORY&status=inactive&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1-25 of 121 warehouses | Page 1 of 5')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'WH-HISTORY',status:'inactive',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  for(const size of [50,100]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),size);
  }
  await navigate(manager,filters.replace('page_size=25','page_size=100')+'&page=2');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),21);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('WH-HISTORY-0120')`),true);
  await navigate(manager,'/inventory/warehouses?search=WH%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No warehouses match these filters.')`),true);
  const invalid=await evaluate(manager,`(async()=>{const r=await fetch('/inventory/warehouses?status=bogus');return [r.status,(await r.text()).includes('Warehouses were not loaded.')];})()`);
  assert.deepEqual(invalid,[400,true]);
  const data={warehouse_code:'WH-BROWSER',warehouse_name:'PRIVATE warehouse name',location:'PRIVATE <img src=x onerror=alert(1)>'};
  async function submit(values,forged=false){
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(key).value=value;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  await navigate(manager,'/inventory/warehouses/add');await submit({...data,location:'x'.repeat(256)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('255 characters')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="location"]').value.length`),256);
  assert.equal(await evaluate(manager,`document.querySelector('[name="warehouse_name"]').value`),data.warehouse_name);
  await submit(data);await until(manager,`location.pathname==='/inventory/warehouses' && document.readyState==='complete'`);
  await navigate(manager,'/inventory/warehouses/add');await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('already exists')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="location"]').value`),data.location);
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await navigate(manager,'/inventory/warehouses?search=WH-BROWSER');
  const edit=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
  await navigate(manager,edit);await submit(data);
  await until(manager,`location.pathname==='/inventory/warehouses' && document.body.textContent.includes('No warehouse changes were needed.')`);
  await navigate(manager,edit);await submit({...data,warehouse_name:'PRIVATE revised warehouse'});
  await until(manager,`location.pathname==='/inventory/warehouses' && document.readyState==='complete'`);
  for(const target of ['0','1']){
    await navigate(manager,'/inventory/warehouses?search=WH-BROWSER');
    const result=await evaluate(manager,`(async()=>{const f=document.querySelector('main tbody form');const data=new URLSearchParams(new FormData(f));const action=f.action;const target=data.get('is_active');const a=await fetch(action,{method:'POST',body:data});const b=await fetch(action,{method:'POST',body:data});return [target,a.status,b.status,(await b.text()).includes('status was not changed')];})()`);
    assert.deepEqual(result,[target,200,200,true]);
  }
  const viewer=await login('denied-user');
  await navigate(viewer,'/inventory/warehouses?search=WH-HISTORY');
  assert.equal(await evaluate(viewer,`document.querySelectorAll('main tbody form,main tbody a').length`),0);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch('/inventory/warehouses/add');return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(edit.replace('/edit','/status'))},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  console.log('PASS Chrome Warehouse 25/50/100 pages, exact counts, preserved filters, historical/empty/invalid states, retained escaped forms, create/edit/no-op, duplicate, explicit repeated status, view-only permission and CSRF denial');
};
