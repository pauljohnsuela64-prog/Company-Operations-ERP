// Visual checks on native routes of a verified disposable server; no production data.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
module.exports=async({send,tab,evaluate,navigate,until,errors,phase,artifacts})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard'&&document.readyState==='complete'`);return t;
  }
  const routes={stock:['/inventory/stock','/inventory/stock/in','/inventory/stock/out','/inventory/stock/movements','/inventory/stock/reconciliation','/inventory/stock/movements?q=NO-GUI-MATCH','/inventory/stock/movements?page_size=invalid']};
  const manager=await login('review-user'),reader=await login('denied-user');
  for(const [role,t] of [['manager',manager],['reader',reader]]){
    for(const w of [1440,1024,768,390,320]){
      await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},t);
      for(const url of (phase==='all'?Object.values(routes).flat():routes[phase])){
        if(role==='reader'&&/\/(in|out)$/.test(url))continue;
        await navigate(t,url);
        await evaluate(t,'new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
        const result=await evaluate(t,`(()=>{
          const root=document.querySelector('main')||document.body;
          const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);
          const missing=[...root.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e=>!e.id||![...document.querySelectorAll('label')].some(l=>l.htmlFor===e.id)).map(e=>e.name);
          const overlap=[...root.querySelectorAll('.workspace-filters,.workflow-actions')].some(group=>{const boxes=[...group.children].filter(e=>getComputedStyle(e).display!=='none').map(e=>e.getBoundingClientRect());return boxes.some((a,i)=>boxes.slice(i+1).some(b=>a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1));});
          return {overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,missing,duplicate:ids.length!==new Set(ids).size,overlap,error:document.body.textContent.includes('Internal Server Error'),h1:root.querySelectorAll('h1').length};
        })()`);
        assert.deepEqual(result,{overflow:false,missing:[],duplicate:false,overlap:false,error:false,h1:1},role+' '+w+' '+url);
        if(role==='reader'&&url==='/inventory/stock')assert.equal(await evaluate(t,`document.querySelectorAll('main a[href$="/in"],main a[href$="/out"]').length`),0);
        for(const region of await evaluate(t,`[...document.querySelectorAll('.workspace-table-scroll')].map((e,i)=>({i,max:e.scrollWidth-e.clientWidth}))`)){
          if(region.max>0)assert(await evaluate(t,`(()=>{const e=document.querySelectorAll('.workspace-table-scroll')[${region.i}];e.focus();e.scrollLeft=20;return e.scrollLeft>0})()`),'table does not scroll');
        }
        await evaluate(t,'window.scrollTo(0,0)');
        const {data}=await send('Page.captureScreenshot',{format:'png'},t);
        fs.writeFileSync(path.join(artifacts,`${phase}-${role}-${w}-${url.replace(/[^a-z0-9]/gi,'_')}.png`),Buffer.from(data,'base64'));
      }
    }
  }
  // Forged invalid stock quantity must retain the idempotency identity and values.
  if(phase==='stock'||phase==='all'){
    await navigate(manager,'/inventory/stock/in');
    const identity=await evaluate(manager,`document.querySelector('[name=submission_id]').value`);
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');f.item_id.value='990';f.warehouse_id.value='990';f.quantity.value='-1';HTMLFormElement.prototype.submit.call(f)})()`);
    await until(manager,`document.readyState==='complete'&&document.querySelector('[name=quantity]')?.value==='-1'`);
    assert.equal(await evaluate(manager,`document.querySelector('[name=submission_id]').value`),identity);
    assert(await evaluate(manager,`document.querySelector('.alert-danger')!==null`));
  }
  assert.equal(errors.length,0,JSON.stringify(errors));
  console.log('PASS GUI '+phase+': native manager/reader routes at 1440/1024/768/390/320; labels, unique IDs, contained tables, no page overflow/overlap or JS exceptions');
};
