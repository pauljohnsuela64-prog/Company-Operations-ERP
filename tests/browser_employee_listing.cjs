// Native GET forms, navigation and responsive listing on the disposable server.
const assert = require('node:assert/strict');
module.exports = async ({send,tab,evaluate,navigate,until}) => {
  async function login(username) {
    const {browserContextId}=await send('Target.createBrowserContext');
    const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(() => {
      document.querySelector('[name="username"]').value=${JSON.stringify(username)};
      document.querySelector('[name="password"]').value='review-password';
      document.querySelector('form').requestSubmit();
    })()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);
    return t;
  }
  const manager=await login('review-user');
  await navigate(manager,'/employees');
  assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody tr').length`),25);
  await evaluate(manager,`(() => {
    const f=document.querySelector('main form');f.elements.search.value=' LIST-SYN- ';f.requestSubmit();
  })()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('63 matching employees')`);
  assert.equal(await evaluate(manager,`document.querySelector('#employee-search').value`),'LIST-SYN-');
  const collected=[];
  for (let page=1;page<=3;page++) {
    assert(await evaluate(manager,`document.body.textContent.includes('Page ${page} of 3')`));
    collected.push(...await evaluate(manager,`[...document.querySelectorAll('main tbody tr')].map(r=>r.cells[0].textContent.trim())`));
    if(page<3) {
      await evaluate(manager,`document.querySelector('main a[rel="next"]').click()`);
      await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Page ${page+1} of 3')`);
      assert.equal(await evaluate(manager,`new URLSearchParams(location.search).get('search')`),'LIST-SYN-');
    }
  }
  assert.equal(collected.length,63);assert.equal(new Set(collected).size,63);
  assert.deepEqual(collected,[...collected].sort());
  assert.equal(await evaluate(manager,`document.querySelector('main a[rel="next"]')===null`),true);
  await evaluate(manager,`document.querySelector('main a[rel="prev"]').click()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('Page 2 of 3')`);
  await evaluate(manager,`(() => {const f=document.querySelector('main form');f.elements.search.value='LIST%';f.requestSubmit();})()`);
  await until(manager,`document.readyState==='complete' && document.body.textContent.includes('1 matching employee.')`);
  assert.equal(await evaluate(manager,`new URLSearchParams(location.search).has('page')`),false);
  assert(await evaluate(manager,`document.querySelector('main tbody').textContent.includes('LIST%LITERAL')`));
  for (const [term,expected] of [['LIST_',1],['José',1],['LIST!',1],["' OR 1=1 --",0],['<img',1],['absent-synthetic',0]]) {
    await evaluate(manager,`(() => {const f=document.querySelector('main form');f.elements.search.value=${JSON.stringify(term)};f.requestSubmit();})()`);
    await until(manager,`document.readyState==='complete' && document.querySelector('#employee-search').value===${JSON.stringify(term)} && document.body.textContent.includes('${expected} matching employee')`);
    assert.equal(await evaluate(manager,`document.querySelectorAll('main tbody img, main form img').length`),0);
    if(expected===0)assert(await evaluate(manager,`document.body.textContent.includes('No employees match your search.')`));
  }
  await navigate(manager,'/employees?page=0');
  assert(await evaluate(manager,`document.querySelector('[role="alert"]').textContent.includes('Page must')`));
  await navigate(manager,'/employees?search=LIST-SYN-&page=999999999');
  assert(await evaluate(manager,`document.body.textContent.includes('Page 3 of 3')`));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},manager);
  await evaluate(manager,`document.querySelector('main a.btn[href="/employees"]').click()`);
  await until(manager,`location.search==='' && document.readyState==='complete'`);
  assert.equal(await evaluate(manager,`document.querySelector('#employee-search').value`),'');
  assert(await evaluate(manager,`document.documentElement.scrollWidth<=innerWidth+2`));
  assert(await evaluate(manager,`!!document.querySelector('main a[href="/employees/add"]')`));
  const viewer=await login('listing-viewer');
  await navigate(viewer,'/employees?search=LIST-SYN-');
  assert(await evaluate(viewer,`document.body.textContent.includes('63 matching employees')`));
  assert.equal(await evaluate(viewer,`document.querySelectorAll('main a[href$="/add"],main a[href$="/edit"]').length`),0);
  const denied=await login('denied-user');
  const deniedResult=await evaluate(denied,`(async()=>{const r=await fetch('/employees?search=LIST-SYN-');return {path:new URL(r.url).pathname,body:await r.text()};})()`);
  assert.equal(deniedResult.path,'/dashboard');
  assert(!deniedResult.body.includes('63 matching employees'));
  console.log('PASS Chrome Employee native search/reset, first/middle/last navigation, literal prefixes, Unicode, injection/HTML safety, responsive layout and viewer/denied roles');
};
