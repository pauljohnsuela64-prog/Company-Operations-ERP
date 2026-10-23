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
  const routes={
  "polish": [
    "/it/assets", "/it/assets?search=NO-GUI-MATCH", "/it/assets/990", "/it/assets/991",
    "/finance/budgets", "/finance/budgets?search=NO-GUI-MATCH",
    "/payroll/periods/990", "/payroll/periods/991"
  ],
  "empty": [
    "/inventory/stock/movements?q=NO-GUI-MATCH",
    "/inventory/stock/reconciliation?item_id=999999",
    "/finance/expenses?search=NO-GUI-MATCH",
    "/finance/budgets?search=NO-GUI-MATCH",
    "/employees?search=NO-GUI-MATCH",
    "/attendance?search=NO-GUI-MATCH",
    "/leave/requests?search=NO-GUI-MATCH",
    "/it/assets?search=NO-GUI-MATCH",
    "/it/help-desk?search=NO-GUI-MATCH",
    "/admin/audit-logs?module=NO-GUI-MATCH"
  ],
  "previous": [
    "/dashboard",
    "/procurement/requests",
    "/procurement/orders",
    "/procurement/receipts",
    "/inventory/categories",
    "/inventory/items",
    "/inventory/warehouses",
    "/finance/expense-categories"
  ],
  "admin": [
    "/admin/users",
    "/admin/users/add",
    "/admin/users/2/reset-password",
    "/admin/roles",
    "/admin/roles/1/permissions",
    "/admin/audit-logs",
    "/logout"
  ],
  "it": [
    "/it/assets",
    "/it/assets/add",
    "/it/assets/990",
    "/it/assets/990/edit",
    "/it/assets/991",
    "/it/assets/990/maintenance/add",
    "/it/assets/categories",
    "/it/assets/categories/add",
    "/it/assets/categories/990/edit",
    "/it/assets/reports",
    "/it/help-desk",
    "/it/help-desk/add",
    "/it/help-desk/990",
    "/it/help-desk/991",
    "/it/help-desk/reports"
  ],
  "hr": [
    "/departments",
    "/departments/add",
    "/departments/990/edit",
    "/employees",
    "/employees/add",
    "/employees/990/edit",
    "/attendance",
    "/attendance/add",
    "/attendance/990/edit",
    "/leave/types",
    "/leave/types/add",
    "/leave/types/990/edit",
    "/leave/requests",
    "/leave/requests/add",
    "/leave/requests/990",
    "/leave/balances",
    "/leave/reports",
    "/payroll/periods",
    "/payroll/periods/add",
    "/payroll/periods/990",
    "/payroll/periods/991",
    "/payroll/periods/990/edit",
    "/payroll/compensation",
    "/payroll/compensation/add",
    "/payroll/compensation/990/edit",
    "/payroll/entries/990",
    "/payroll/entries/991/payslip"
  ],
  "finance": [
    "/finance",
    "/finance/expenses",
    "/finance/expenses/add",
    "/finance/expenses/990",
    "/finance/expenses/990/edit",
    "/finance/budgets",
    "/finance/budgets/add",
    "/finance/budgets/990",
    "/finance/budgets/990/edit",
    "/finance/reports",
    "/finance/expenses?search=NO-GUI-MATCH"
  ],
  "stock": [
    "/inventory/stock",
    "/inventory/stock/in",
    "/inventory/stock/out",
    "/inventory/stock/movements",
    "/inventory/stock/reconciliation",
    "/inventory/stock/movements?q=NO-GUI-MATCH",
    "/inventory/stock/movements?page_size=invalid"
  ]
};
  const manager=await login('review-user'),reader=await login('denied-user');
  const approver=(phase==='hr'||phase==='finance'||phase==='all')?await login('gui-approver'):null;
  for(const [role,t] of [['manager',manager],['reader',reader],...(approver?[['approver',approver]]:[])]){
    for(const w of [1440,1024,768,390,320]){
      await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},t);
      for(const url of (phase==='all'?Object.values(routes).flat():routes[phase])){
        if(role!=='manager'&&(/\/(in|out|add|edit|reset-password)$/.test(url)))continue;
        if(role==='reader'&&url.startsWith('/admin/')&&!url.startsWith('/admin/audit-logs'))continue;
        if(role==='approver'&&!url.startsWith('/finance')&&!url.startsWith('/leave')&&!url.startsWith('/payroll'))continue;
        if(role==='approver'&&url.startsWith('/leave')&&!/\/(requests|990)$/.test(url))continue;
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
        if(phase==='polish'){
          assert(await evaluate(t,`document.querySelector('.workspace-heading .workspace-table')===null`),'page data must be outside the heading');
          if(/\/it\/assets\/99[01]$/.test(url))assert(await evaluate(t,`[...document.querySelectorAll('main .card .card')].length===0`),'asset lifecycle panels must be siblings');
        }
        if(phase==='empty'){
          assert(await evaluate(t,`[...document.querySelectorAll('.modern-page .workspace-table')].every(table=>{
            const placeholder=table.querySelector('tbody > tr:only-child > td[colspan]:only-child');
            if(!placeholder)return true;
            const region=table.closest('.workspace-table-scroll');
            return (!table.tHead||getComputedStyle(table.tHead).display==='none')&&table.scrollWidth<=region.clientWidth+1;
          })`),'empty-state message must fit the scroll container');
        }
        if(/\/payroll\/periods\/99[01]$/.test(url)){
          assert(await evaluate(t,`[...document.querySelectorAll('main tbody tr')].filter(r=>!r.querySelector('[colspan]')).every(r=>r.cells.length===11&&r.querySelectorAll('a[href^="/payroll/entries/"]:not([href$="/payslip"])').length===1)`),'Payroll table columns/actions must align');
        }
        if(role==='reader'&&url==='/inventory/stock')assert.equal(await evaluate(t,`document.querySelectorAll('main a[href$="/in"],main a[href$="/out"]').length`),0);
        for(const region of await evaluate(t,`[...document.querySelectorAll('.workspace-table-scroll')].map((e,i)=>({i,max:e.scrollWidth-e.clientWidth}))`)){
          if(region.max>0)assert(await evaluate(t,`(()=>{const e=document.querySelectorAll('.workspace-table-scroll')[${region.i}];e.focus();e.scrollLeft=20;return e.scrollLeft>0})()`),'table does not scroll');
        }
        await evaluate(t,'window.scrollTo(0,0)');
        const {contentSize}=await send('Page.getLayoutMetrics',{},t);
        const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:w,height:Math.min(contentSize.height,2400),scale:1}},t);
        fs.writeFileSync(path.join(artifacts,`${phase}-${role}-${w}-${url.replace(/[^a-z0-9]/gi,'_')}.png`),Buffer.from(data,'base64'));
      }
    }
  }
  if(phase==='admin'||phase==='all'){
    const {browserContextId}=await send('Target.createBrowserContext');const anonymous=await tab(browserContextId);
    for(const w of [1440,1024,768,390,320]){
      for(const t of [anonymous,manager])await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},t);
      await navigate(anonymous,'/login');
      for(const invalid of [false,true]){
        if(invalid){
          await evaluate(anonymous,`(()=>{const f=document.querySelector('form');f.username.value='gui-invalid';f.password.value='synthetic-invalid';f.requestSubmit()})()`);
          await until(anonymous,`document.readyState==='complete'&&document.body.textContent.includes('Invalid username or password.')`);
        }
        assert(await evaluate(anonymous,`document.documentElement.scrollWidth<=innerWidth&&document.querySelectorAll('h1').length===1&&[...document.querySelectorAll('input:not([type=hidden])')].every(e=>[...document.querySelectorAll('label')].some(l=>l.htmlFor===e.id))`));
        const {data}=await send('Page.captureScreenshot',{format:'png'},anonymous);
        fs.writeFileSync(path.join(artifacts,`login-${invalid?'error':'empty'}-${w}.png`),Buffer.from(data,'base64'));
      }
      await navigate(manager,'/logout');
      await evaluate(manager,`(()=>{const f=document.querySelector('main form');f.csrf_token.value='invalid';f.requestSubmit()})()`);
      await until(manager,`document.readyState==='complete'&&document.body.textContent.includes('Submission not processed')`);
      assert(await evaluate(manager,`document.documentElement.scrollWidth<=innerWidth&&document.querySelectorAll('main h1').length===1`));
      const {data}=await send('Page.captureScreenshot',{format:'png'},manager);
      fs.writeFileSync(path.join(artifacts,`csrf-error-${w}.png`),Buffer.from(data,'base64'));
    }
  }
  const invalidCases=[
    ['stock','/inventory/stock/in',{item_id:'990',warehouse_id:'990',quantity:'-1'},'quantity','-1'],
    ['finance','/finance/expenses/add',{expense_date:'2026-10-23',category_id:'990',description:'GUI validation',amount:'-1'},'amount','-1'],
    ['hr','/employees/add',{employee_number:'G'.repeat(31),first_name:'GUI',last_name:'Validation'},'employee_number','G'.repeat(31)],
    ['it','/it/assets/add',{asset_tag:'G'.repeat(51),asset_name:'GUI validation',category_id:'990'},'asset_tag','G'.repeat(51)],
    ['it','/it/help-desk/add',{employee_id:'990',category_id:'1',subject:'S'.repeat(151),description:'GUI validation',priority:'HIGH'},'subject','S'.repeat(151)]
  ];
  for(const [key,url,values,field,value] of invalidCases){
    if(phase!=='all'&&phase!==key)continue;
    for(const w of [390,320]){
      await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},manager);
      await navigate(manager,url);
      await evaluate(manager,`(()=>{const f=document.querySelector('main form');for(const [k,v] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(k).value=v;HTMLFormElement.prototype.submit.call(f)})()`);
      await until(manager,`document.readyState==='complete'&&document.querySelector('.alert-danger')!==null`);
      assert.equal(await evaluate(manager,`document.querySelector('[name="${field}"]').value`),value);
      assert(await evaluate(manager,`document.documentElement.scrollWidth<=innerWidth`),'validation page overflow');
      const {contentSize}=await send('Page.getLayoutMetrics',{},manager);
      const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:w,height:Math.min(contentSize.height,2400),scale:1}},manager);
      fs.writeFileSync(path.join(artifacts,`validation-${key}-${field}-${w}.png`),Buffer.from(data,'base64'));
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
  if(phase==='hr'||phase==='all'){
    assert.equal(await evaluate(manager,`(async()=>new URL((await fetch('/payroll/entries/990/payslip')).url).pathname)()`),'/payroll/entries/990','unpaid payslip guard');
    await navigate(manager,'/payroll/entries/991/payslip');
    await send('Emulation.setEmulatedMedia',{media:'print'},manager);
    assert(await evaluate(manager,`getComputedStyle(document.querySelector('.topbar')).display==='none'&&document.body.textContent.includes('Employee Payslip')`));
    const {data:pdf}=await send('Page.printToPDF',{printBackground:false,preferCSSPageSize:true},manager);
    fs.writeFileSync(path.join(artifacts,'paid-payslip-print.pdf'),Buffer.from(pdf,'base64'));
    const {data:printShot}=await send('Page.captureScreenshot',{format:'png'},manager);
    fs.writeFileSync(path.join(artifacts,'paid-payslip-print.png'),Buffer.from(printShot,'base64'));
    await send('Emulation.setEmulatedMedia',{media:''},manager);
  }
  if(phase==='empty'){
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:false},manager);
    await navigate(manager,'/inventory/stock');
    await evaluate(manager,`(()=>{const e=document.querySelector('.workspace-table-scroll');e.focus();e.scrollLeft=0;})()`);
    assert(await evaluate(manager,`getComputedStyle(document.activeElement).outlineStyle==='solid'&&document.activeElement.tabIndex===0`));
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39},manager);
    await until(manager,`document.querySelector('.workspace-table-scroll').scrollLeft>0`);
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39},manager);
    const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);
    await navigate(t,'/login');
    assert.equal(await evaluate(t,'document.activeElement.name'),'username');
    for(const expected of ['password','submit']){
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9},t);
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9},t);
      assert.equal(await evaluate(t,`document.activeElement.name||document.activeElement.type`),expected);
    }
    console.log('PASS keyboard: focused table scrolls with ArrowRight; login Tab order reaches password and submit');
  }
  assert.equal(errors.length,0,JSON.stringify(errors));
  console.log('PASS GUI '+phase+': native manager/reader routes at 1440/1024/768/390/320; labels, unique IDs, contained tables, no page overflow/overlap or JS exceptions');
};
