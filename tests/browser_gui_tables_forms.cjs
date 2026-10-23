// Composed with the unchanged security and module browser workflows.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
module.exports=async({send,tab,evaluate,navigate,until,errors,dialogs,setConfirm,artifacts})=>{
  async function login(username){
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(username)};f.password.value='review-password';f.requestSubmit();})()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);return t;
  }
  async function width(t,w){
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},t);
    await evaluate(t,`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
  }
  async function layout(t){
    assert(await evaluate(t,`Boolean(document.querySelector('link[href*=bootstrap]').sheet)`),'Bootstrap not loaded');
    assert(await evaluate(t,`document.documentElement.scrollWidth<=document.documentElement.clientWidth`),'page-wide overflow');
    const controls=await evaluate(t,`(()=>{
      const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);
      const unique=ids.length===new Set(ids).size;
      return {unique,labels:[...document.querySelectorAll('main input:not([type=hidden]), main select,main textarea')].every(e=>e.id&&[...document.querySelectorAll('label')].some(l=>l.htmlFor===e.id))};
    })()`);
    assert(controls.unique&&controls.labels,'duplicate IDs or missing label association');
    assert.equal(await evaluate(t,`document.querySelectorAll('h1').length`),1);
    assert(await evaluate(t,`['.workspace-filters > div','.workspace-form-grid > div'].every(selector=>{
      const boxes=[...document.querySelectorAll(selector)].map(e=>e.getBoundingClientRect());
      return boxes.every((a,i)=>boxes.slice(i+1).every(b=>!(a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1)));
    })`),'overlapping filter controls or form fields');
  }
  async function shot(t,name,full=false){
    await evaluate(t,'window.scrollTo(0,0)');
    const {contentSize}=await send('Page.getLayoutMetrics',{},t);const w=await evaluate(t,'innerWidth');
    const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:full,...(full?{clip:{x:0,y:0,width:w,height:contentSize.height,scale:1}}:{})},t);
    fs.writeFileSync(path.join(artifacts,name+'.png'),Buffer.from(data,'base64'));
  }
  const manager=await login('review-user'),viewer=await login('denied-user');
  const modules=[
    {key:'suppliers',url:'/procurement/suppliers',history:'SUP-HISTORY',code:'SUP-BROWSER',name:'supplier_name',long:'address',fields:[['supplier_code',30,true,'text'],['supplier_name',150,true,'text'],['contact_person',100,false,'text'],['email',150,false,'text'],['phone',30,false,'text'],['address',255,false,'textarea']]},
    {key:'categories',url:'/finance/expense-categories',history:'EXP-HISTORY',code:'EXP-BROWSER',name:'category_name',long:'description',fields:[['category_code',30,true,'text'],['category_name',100,true,'text'],['description',255,false,'textarea']]}
  ];
  for(const m of modules){
    let edit;
    for(const [role,t] of [['manager',manager],['viewer',viewer]]){
      for(const w of [1440,1024,768,390,320]){
        await width(t,w);await navigate(t,m.url+'?search='+m.history+'&status=inactive&page_size=25');await layout(t);
        assert.equal(await evaluate(t,`document.querySelectorAll('main tbody tr').length`),25);
        assert(await evaluate(t,`[...document.querySelectorAll('main thead th')].every(e=>e.scope==='col')&&Boolean(document.querySelector('caption'))`));
        assert.equal(await evaluate(t,`document.querySelectorAll('main img').length`),0,'unescaped fixture text');
        const scroll=await evaluate(t,`(()=>{const e=document.querySelector('.workspace-table-scroll');e.focus();e.scrollLeft=e.scrollWidth;return {x:e.scrollLeft,max:e.scrollWidth-e.clientWidth,focus:getComputedStyle(e).outlineStyle}})()`);
        if(scroll.max>0) assert(scroll.x>0,'overflowing table must scroll within its region');
        if(w<=768) assert(scroll.max>0,'narrow tables should retain all columns in a scroll region');
        assert.equal(scroll.focus,'solid');
        await evaluate(t,`document.querySelector('.workspace-table-scroll').scrollLeft=0`);
        if(scroll.max>0){
          await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39},t);
          await until(t,`document.querySelector('.workspace-table-scroll').scrollLeft>0`);
          await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39},t);
          await evaluate(t,`document.querySelector('.workspace-table-scroll').scrollLeft=0`);
        }
        if(role==='viewer') assert.equal(await evaluate(t,`document.querySelectorAll('main a[href$="/edit"],main a[href$="/add"],main form[method=POST]').length`),0);
        await shot(t,`${m.key}-${role}-${w}`);
        await navigate(t,m.url+'?search=NO-MATCH-FOR-GUI');await layout(t);
        assert(await evaluate(t,`document.body.textContent.includes('No matching records')&&!document.body.textContent.includes('Unable to display records')`));
        if(w===1440||w===320) await shot(t,`${m.key}-${role}-empty-${w}`);
        await navigate(t,m.url+'?__gui_outage=1');await layout(t);
        assert(await evaluate(t,`document.body.textContent.includes('Unable to display records')&&!document.body.textContent.includes('No matching records')`));
        if(w===1440||w===320) await shot(t,`${m.key}-${role}-unavailable-${w}`);
        if(role==='manager'){
          await navigate(t,m.url+'?search='+m.code);
          edit=await evaluate(t,`document.querySelector('main tbody a').getAttribute('href')`);
          for(const [kind,url] of [['add',m.url+'/add'],['edit',edit]]){
            await navigate(t,url);await layout(t);
            for(const [name,max,required,type] of m.fields){
              const actual=await evaluate(t,`(()=>{const e=document.querySelector('[name="${name}"]');return [e.maxLength,e.required,e.tagName==='TEXTAREA'?'textarea':e.type]})()`);
              assert.deepEqual(actual,[max,required,type]);
            }
            assert(await evaluate(t,`Boolean(document.querySelector('main form [name=csrf_token]'))`));
            await shot(t,`${m.key}-${kind}-${w}`,true);
          }
        }
      }
    }
    // Retained validation values/escaping on the actual form route, no writes.
    await width(manager,390);await navigate(manager,edit);
    await evaluate(manager,`(()=>{const f=document.querySelector('main form');f.elements.namedItem('${m.long}').value='x'.repeat(256);HTMLFormElement.prototype.submit.call(f);})()`);
    await until(manager,`document.readyState==='complete'&&document.body.textContent.includes('255 characters')`);await layout(manager);
    assert.equal(await evaluate(manager,`document.querySelector('[name="${m.long}"]').value.length`),256);
    await shot(manager,`${m.key}-validation-390`,true);
    await navigate(manager,m.url+'?search='+m.code);
    if(m.key==='suppliers'){
      setConfirm(false);
      await evaluate(manager,`document.querySelector('main tbody button').click()`);
      assert.equal(dialogs.at(-1),'Deactivate this supplier?');
      assert(await evaluate(manager,`document.querySelector('main tbody [name=is_active]').value==='0'`));
      setConfirm(true);
    }
    for(const active of [false,true]){
      await evaluate(manager,`document.querySelector('main tbody button').click()`);
      await until(manager,`document.readyState==='complete'&&document.body.textContent.includes('${active?'activated':'deactivated'} successfully.')`);
      await navigate(manager,m.url+'?search='+m.code);
      assert.equal(await evaluate(manager,`document.querySelector('main tbody [name=is_active]').value`),active?'0':'1');
    }
    console.log('PASS Phase 2 '+m.key+': manager/viewer at 1440/1024/768/390/320; populated/long/empty/unavailable tables, labeled forms and retained validation, contained scrolling, explicit native status actions');
  }
  assert.equal(errors.length,0,`JavaScript errors: ${errors}`);
  console.log('PASS GUI Phase 2: unchanged GET/POST contracts exercised by original module browser suites; no console.error or uncaught JavaScript exceptions');
};
