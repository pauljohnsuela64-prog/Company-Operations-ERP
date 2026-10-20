// Native Help Desk forms on the verified disposable security-review server.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until,fixture})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/it/help-desk?search=HELP-BROWSER&status=CANCELLED&priority=HIGH&category_id='+fixture.historicalCategory+'&assigned_to=5&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('61 tickets')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'HELP-BROWSER',status:'CANCELLED',priority:'HIGH',category_id:String(fixture.historicalCategory),assigned_to:'5',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);assert.equal(await evaluate(manager,`document.body.textContent.includes('Page 2 of 3')`),true);
  for(const [size,count] of [[50,50],[100,61]]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),count);
  }
  await navigate(manager,'/it/help-desk?search=HELP%25');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr a').length`),0);
  const data={employee_id:String(fixture.employee),category_id:String(fixture.category),subject:'HELP-BROWSER newly created',description:'PRIVATE <img src=x onerror=alert(1)> description',priority:'HIGH'};
  async function submit(values,forged=false){
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [key,value] of Object.entries(${JSON.stringify(values)})){const el=f.elements.namedItem(key);if(el.tagName==='SELECT' && ![...el.options].some(o=>o.value===value))el.add(new Option('Forged reference',value));el.value=value;} ${forged?'HTMLFormElement.prototype.submit.call(f)':'f.requestSubmit()'};})()`);
  }
  await navigate(manager,'/it/help-desk/add');await submit({...data,subject:'X'.repeat(151)},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Subject must not exceed 150 characters.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="subject"]').value`),'X'.repeat(151));
  assert.equal(await evaluate(manager,`document.querySelector('[name="description"]').value`),data.description);
  await submit({...data,category_id:'999999'},true);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Selected category is invalid or inactive.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="category_id"]').value`),'999999');
  await submit(data);await until(manager,`location.pathname==='/it/help-desk' && document.readyState==='complete'`);
  await navigate(manager,'/it/help-desk?search='+encodeURIComponent(data.subject));
  const detail=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
  await navigate(manager,detail);
  assert.equal(await evaluate(manager,`document.querySelector('main img[src="x"]')===null`),true);
  await evaluate(manager,`(()=>{const f=document.querySelector('form[action$="/assign"]');f.assigned_to.add(new Option('Invalid','999999'));f.assigned_to.value='999999';f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Selected technician is invalid or inactive.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="assigned_to"]').value`),'999999');
  await evaluate(manager,`(()=>{const f=document.querySelector('form[action$="/assign"]');f.assigned_to.value='6';f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Technician assigned successfully.')`);
  await evaluate(manager,`document.querySelector('form[action$="/start"]').requestSubmit()`);
  await until(manager,`document.readyState==='complete' && !!document.querySelector('form[action$="/resolve"]')`);
  await evaluate(manager,`(()=>{const f=document.querySelector('form[action$="/resolve"]');f.resolution.value='R'.repeat(65536);f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Resolution must not exceed 65535 characters.')`);
  assert.equal(await evaluate(manager,`document.querySelector('[name="resolution"]').value.length`),65536);
  await evaluate(manager,`(()=>{const f=document.querySelector('form[action$="/resolve"]');f.resolution.value='PRIVATE resolution';f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && !!document.querySelector('form[action$="/close"]')`);
  await evaluate(manager,`document.querySelector('form[action$="/close"]').requestSubmit()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Ticket closed successfully.')`);
  const repeated=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(detail+'/close')},{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return r.status;})()`);assert.equal(repeated,409);
  const csrf=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(detail+'/assign')},{method:'POST',body:new URLSearchParams({assigned_to:'6',csrf_token:'bad'})});return r.status;})()`);assert.equal(csrf,400);
  const viewer=await login('helpdesk-viewer');await navigate(viewer,detail);
  assert.equal(await evaluate(viewer,`document.querySelector('main form')===null`),true);
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(detail+'/close')},{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name="csrf-token"]').content})});return new URL(r.url).pathname;})()`);assert.equal(denied,'/dashboard');
  await navigate(manager,'/admin/audit-logs?module=HELP_DESK&action=RESOLVE');
  const auditText=await evaluate(manager,`document.querySelector('main tbody').textContent`);
  assert(auditText.includes('Help Desk ticket '+detail.split('/').pop()+': resolve committed.'));
  assert(!auditText.includes('PRIVATE'));
  console.log('PASS Chrome Help Desk 25/50/100 pages, exact filtered counts, preserved category/priority/technician filters, literal search, retained/escaped forms, create/assign/start/resolve/close, repeated transition, CSRF and viewer denial');
};
