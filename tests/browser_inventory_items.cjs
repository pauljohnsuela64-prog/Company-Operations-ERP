// Native Items checks against the verified disposable security-review instance.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/inventory/items?search=ITEM-HISTORY&category_id=none&status=inactive&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1-25 of 121 items | Page 1 of 5')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'ITEM-HISTORY',category_id:'none',status:'inactive',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  for(const size of [50,100]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),size);
  }
  await navigate(manager,filters.replace('page_size=25','page_size=100')+'&page=999');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),21);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('ITEM-HISTORY-0120')`),true);
  await navigate(manager,'/inventory/items?search=ITEM%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No inventory items match these filters.')`),true);
  const invalid=await evaluate(manager,`(async()=>{const results=[];for(const q of ['status=bad','category_id=bad','page_size=500','search=x&search=y']){const r=await fetch('/inventory/items?'+q);results.push([r.status,(await r.text()).includes('Inventory items were not loaded.')]);}return results;})()`);
  for(const result of invalid)assert.deepEqual(result,[400,true]);
  const data={item_code:'ITEM-BROWSER',item_name:'PRIVATE item name',category_id:'',unit_of_measure:'pcs',reorder_level:'0.10',description:'PRIVATE <img src=x onerror=alert(1)>'};
  async function submit(values,forged=false){
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(key).value=value;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  await navigate(manager,'/inventory/items/add');await submit({...data,reorder_level:'NaN'},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('finite')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="reorder_level"]').value`),'NaN');
  assert.equal(await evaluate(manager,`document.querySelector('[name="description"]').value`),data.description);
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await submit(data);await until(manager,`location.pathname==='/inventory/items' && document.readyState==='complete'`);
  await navigate(manager,'/inventory/items/add');await submit(data);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('already exists')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="description"]').value`),data.description);
  await navigate(manager,'/inventory/items?search=ITEM-BROWSER');
  const edit=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
  await navigate(manager,edit);await submit(data);
  await until(manager,`location.pathname==='/inventory/items' && document.body.textContent.includes('No inventory item changes were needed.')`);
  await navigate(manager,edit);await submit({...data,item_name:'PRIVATE revised item',unit_of_measure:'box'});
  await until(manager,`location.pathname==='/inventory/items' && document.readyState==='complete'`);
  await navigate(manager,'/inventory/items?search=ITEM-BROWSER');
  const status=edit.replace('/edit','/status');
  for(const target of ['0','0','1']){
    const result=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'${target}',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return [r.status,new URL(r.url).pathname];})()`);
    assert.deepEqual(result,[200,'/inventory/items']);
  }
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:'invalid'})});return r.status;})()`);
  assert.equal(csrf,400);
  const viewer=await login('denied-user');await navigate(viewer,'/inventory/items?search=ITEM-BROWSER');
  assert.equal(await evaluate(viewer,`document.querySelectorAll('main a[href$="/edit"],main form[method="POST"],main a[href$="/add"]').length`),0);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(status)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome Items 25/50/100 pages, preserved filters/counts, literal/invalid filters, escaped retained values, duplicate/no-op edits, explicit status replay, permissions and CSRF');
};
