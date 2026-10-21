// Native Categories checks against the verified disposable security-review instance.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/inventory/categories?search=CAT-HISTORY&status=inactive&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1-25 of 121 categories | Page 1 of 5')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'CAT-HISTORY',status:'inactive',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  for(const size of [50,100]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),size);
  }
  await navigate(manager,filters.replace('page_size=25','page_size=100')+'&page=999');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),21);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('CAT-HISTORY-0120')`),true);
  await navigate(manager,'/inventory/categories?search=ITEM%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No inventory categories match these filters.')`),true);
  const invalid=await evaluate(manager,`(async()=>{const results=[];for(const q of ['status=bad','page_size=500','search=x&search=y']){const r=await fetch('/inventory/categories?'+q);results.push([r.status,(await r.text()).includes('Inventory categories were not loaded.')]);}return results;})()`);
  for(const result of invalid)assert.deepEqual(result,[400,true]);
  const data={category_code:'CAT-BROWSER',category_name:'PRIVATE category name',description:'PRIVATE <img src=x onerror=alert(1)>'};
  async function submit(values,forged=false){
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(key).value=value;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  await navigate(manager,'/inventory/categories/add');await submit({...data,description:'x'.repeat(256)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('255 characters')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="description"]').value.length`),256);
  assert.equal(await evaluate(manager,`document.querySelector('[name="category_name"]').value`),data.category_name);
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await submit(data);await until(manager,`location.pathname==='/inventory/categories' && document.readyState==='complete'`);
  await navigate(manager,'/inventory/categories/add');await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('already exists')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="description"]').value`),data.description);
  await navigate(manager,'/inventory/categories?search=CAT-BROWSER');
  const edit=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
  await navigate(manager,edit);await submit(data);
  await until(manager,`location.pathname==='/inventory/categories' && document.body.textContent.includes('No inventory category changes were needed.')`);
  await navigate(manager,edit);await submit({...data,category_name:'PRIVATE revised category'});
  await until(manager,`location.pathname==='/inventory/categories' && document.readyState==='complete'`);
  await navigate(manager,'/inventory/categories?search=CAT-BROWSER');
  const status=edit.replace('/edit','/status');
  for(const target of ['0','0','1']){
    const result=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'${target}',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return [r.status,new URL(r.url).pathname];})()`);
    assert.deepEqual(result,[200,'/inventory/categories']);
  }
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  const viewer=await login('denied-user');await navigate(viewer,'/inventory/categories?search=CAT-BROWSER');
  assert.equal(await evaluate(viewer,`document.querySelectorAll('main a[href$="/edit"],main form[method="POST"],main a[href$="/add"]').length`),0);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome Categories 25/50/100 pages, preserved filters/counts, literal/invalid filters, escaped retained values, duplicate/no-op edits, explicit status replay, permissions and CSRF');
};
