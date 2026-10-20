// Read-only Audit Logs navigation on a verified disposable server.
const assert=require('node:assert/strict');
module.exports=async({send,tab,evaluate,navigate,until})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  const manager=await login('review-user');
  const filters='/admin/audit-logs?search=BROWSER-AUDIT&module=BROWSER_AUDIT&action=READ&start_date=2020-01-01&end_date=2020-01-01&page_size=25';
  await navigate(manager,filters);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1-25 of 1005 matching records | Page 1 of 41')`),true);
  const next=await evaluate(manager,`document.querySelector('a[rel="next"]').getAttribute('href')`);
  const parsed=new URL(next,'http://synthetic.invalid');
  for(const [key,value] of Object.entries({search:'BROWSER-AUDIT',module:'BROWSER_AUDIT',action:'READ',start_date:'2020-01-01',end_date:'2020-01-01',page_size:'25',page:'2'}))assert.equal(parsed.searchParams.get(key),value);
  await navigate(manager,next);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 26-50 of 1005 matching records | Page 2 of 41')`),true);
  for(const size of [50,100]){
    await evaluate(manager,`(()=>{const el=document.querySelector('[name="page_size"]');el.value='${size}';el.form.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='${size}'`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),size);
    assert.equal(await evaluate(manager,`new URLSearchParams(location.search).get('search')`),'BROWSER-AUDIT');
  }
  await navigate(manager,filters.replace('page_size=25','page_size=100')+'&page=999');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),5);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('Showing 1001-1005 of 1005 matching records | Page 11 of 11')`),true);
  assert.equal(await evaluate(manager,`document.body.textContent.includes('HIST-0000')`),true);
  assert.equal(await evaluate(manager,`document.querySelector('a[rel="next"]')===null`),true);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main img').length`),0);
  assert.equal(await evaluate(manager,`document.querySelectorAll('main form[method="POST"],main form[method="post"]').length`),0);
  await navigate(manager,'/admin/audit-logs?module=BROWSER_AUDIT&search=BROWSER%25');
  assert.equal(await evaluate(manager,`document.body.textContent.includes('No audit log records match these filters.')`),true);
  await navigate(manager,'/admin/audit-logs?module=NO_SUCH_MODULE');
  assert.equal(await evaluate(manager,`document.querySelector('[name="module"]').value`),'NO_SUCH_MODULE');
  const results=await evaluate(manager,`(async()=>{
    const values=[];for(const query of ['page_size=500','start_date=2026-02-29','start_date=2026-02-01&end_date=2026-01-01','module=BROWSER_AUDIT&module=OTHER','date_from=2020-01-01']){
      const r=await fetch('/admin/audit-logs?'+query);values.push([r.status,(await r.text()).includes('Audit logs were not loaded.')]);
    }
    const good=await fetch('/admin/audit-logs?module=BROWSER_AUDIT');
    values.push([good.status,good.headers.get('Cache-Control'),good.headers.get('Referrer-Policy')]);
    return values;
  })()`);
  for(const result of results.slice(0,5))assert.deepEqual(result,[400,true]);
  assert.equal(results[5][0],200);assert(results[5][1].includes('no-store'));assert.equal(results[5][2],'no-referrer');
  const viewer=await login('denied-user');
  const denied=await evaluate(viewer,`(async()=>{const r=await fetch('/admin/audit-logs?module=BROWSER_AUDIT');return [r.status,new URL(r.url).pathname,(await r.text()).includes('HIST-0000')];})()`);
  assert.deepEqual(denied,[200,'/dashboard',false]);
  console.log('PASS Chrome Audit Logs: 1005 historical rows, 25/50/100 pages, exact counts, retained filters, oldest rows, escaped descriptions, literal wildcards, invalid filters, privacy headers and permission denial');
};
