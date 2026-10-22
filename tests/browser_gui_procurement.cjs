// Real PR -> PO -> partial/full GR workflow on synthetic disposable records.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
module.exports=async({send,tab,evaluate,navigate,until,errors,dialogs,setConfirm,artifacts})=>{
 async function login(name){const {browserContextId}=await send('Target.createBrowserContext');const t=await tab(browserContextId);await navigate(t,'/login');await evaluate(t,`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(name)};f.password.value='review-password';f.requestSubmit();})()`);await until(t,`location.pathname==='/dashboard'&&document.readyState==='complete'`);return t;}
 const manager=await login('procurement.manager'),approver=await login('procurement.approver'),viewer=await login('denied-user'),operator=await login('review-user');
 const long='GUI workflow <img src=x onerror=alert(1)> '+'Long notes '.repeat(15);
 async function shot(t,name){await evaluate(t,'window.scrollTo(0,0)');const {contentSize}=await send('Page.getLayoutMetrics',{},t);const w=await evaluate(t,'innerWidth');const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:w,height:contentSize.height,scale:1}},t);fs.writeFileSync(path.join(artifacts,name+'.png'),Buffer.from(data,'base64'));}
 async function review(t,url,key){
  for(const w of [1440,1024,768,390,320]){
   await send('Emulation.setDeviceMetricsOverride',{width:w,height:1000,deviceScaleFactor:1,mobile:false},t);await navigate(t,url);
   assert(await evaluate(t,`Boolean(document.querySelector('link[href*=bootstrap]').sheet)`));
   const fits=await evaluate(t,`document.documentElement.scrollWidth<=document.documentElement.clientWidth`);
   if(!fits){await shot(t,'overflow-'+key+'-'+w);fs.writeFileSync(path.join(artifacts,'overflow.json'),JSON.stringify(await evaluate(t,`[...document.querySelectorAll('main *')].map(e=>({tag:e.tagName,cls:e.className,w:e.getBoundingClientRect().width,x:e.getBoundingClientRect().x,position:getComputedStyle(e).position})).filter(e=>e.x+e.w>document.documentElement.clientWidth)`),null,2));}
   assert(fits,'overflow '+key+' '+w);
   assert(await evaluate(t,`[...document.querySelectorAll('main input:not([type=hidden]),main select,main textarea')].every(e=>e.id&&[...document.querySelectorAll('label')].some(l=>l.htmlFor===e.id))`),'missing labels '+key);
   assert.equal(await evaluate(t,`document.querySelectorAll('main img[src=x]').length`),0);
   assert(await evaluate(t,`[...document.querySelectorAll('main thead th')].every(e=>e.scope==='col')`));
   if(w<=768)assert(await evaluate(t,`[...document.querySelectorAll('.workspace-table-scroll')].every(e=>{if(e.scrollWidth<=e.clientWidth)return true;e.scrollLeft=e.scrollWidth;const ok=e.scrollLeft>0;e.scrollLeft=0;return ok})`));
   await shot(t,key+'-'+w);
  }
 }
 async function state(url,key,roles=[['manager',manager],['approver',approver],['viewer',viewer]]){for(const [role,t]of roles){await review(t,url,key+'-'+role);if(role==='viewer')assert.equal(await evaluate(t,`document.querySelectorAll('main form[method=POST], main a[href$="/add"],main a[href$="/edit"],main a[href$="/edit-cost"],main a[href$="/create-order"],main a[href$="/receive"],main a[href$="/reject"]').length`),0);}}
 async function submit(t,values,destination,forged=false){await evaluate(t,`(()=>{const f=document.querySelector('main form');for(const[k,v]of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(k).value=v;${forged?'HTMLFormElement.prototype.submit.call(f)':'f.querySelector("button[type=submit]").click()'};})()`);await until(t,`document.readyState==='complete'&&${destination}`);}
 async function action(t,suffix,done){await evaluate(t,`document.querySelector('main form[action$="${suffix}"] button').click()`);await until(t,`document.readyState==='complete'&&${done}`);}
 async function create(purpose){await navigate(manager,'/procurement/requests/add');await submit(manager,{department_id:'900',purpose},`location.pathname==='/procurement/requests'`);return evaluate(manager,`[...document.querySelectorAll('tbody tr')].find(e=>e.textContent.includes(${JSON.stringify(purpose.trim())})).querySelector('a').getAttribute('href')`);}
 async function add(rid,item='900',qty='10.25'){await navigate(manager,rid+'/items/add');await submit(manager,{item_id:item,quantity:qty,estimated_unit_cost:'2.50',notes:long},`location.pathname===${JSON.stringify(rid)}`);}
 for(const url of ['/procurement/requests','/procurement/orders','/procurement/receipts','/procurement/receipts/history'])await review(viewer,url,'empty-'+url.split('/').slice(-2).join('-'));
 await review(manager,'/procurement/requests/add','request-add');
 const primary=await create(long);await add(primary);
 await add(primary,'901','2');
 await navigate(manager,primary);
 const edit=await evaluate(manager,`[...document.querySelectorAll('tbody tr')].find(e=>e.textContent.includes('GUI-SECOND')).querySelector('a').getAttribute('href')`);
 await review(manager,edit,'request-edit-item');await submit(manager,{quantity:'3'},`location.pathname===${JSON.stringify(primary)}`);
 await evaluate(manager,`[...document.querySelectorAll('tbody tr')].find(e=>e.textContent.includes('GUI-SECOND')).querySelector('button').click()`);
 await until(manager,`document.body.textContent.includes('removed successfully.')`);
 await review(manager,primary+'/items/add','request-add-item');
 await navigate(manager,primary+'/items/add');await submit(manager,{item_id:'901',quantity:'0',estimated_unit_cost:'2.50'},`document.querySelector('.alert-danger')!==null`,true);await shot(manager,'request-item-validation');
 await state(primary,'request-draft');
 await navigate(manager,primary);await action(manager,'/submit',`document.body.textContent.includes('submitted successfully.')`);
 await state(primary,'request-submitted');
 assert.equal(await evaluate(manager,`document.querySelectorAll('main form[action$="/approve"]').length`),0);
 await navigate(approver,primary);await action(approver,'/approve',`document.body.textContent.includes('approved successfully.')`);
 await state(primary,'request-approved',[['manager',manager],['approver',approver]]);
 await review(manager,primary+'/create-order','order-create');
 await navigate(manager,primary+'/create-order');
 assert.equal(await evaluate(manager,`document.querySelector('select[name=supplier_id] option[value="901"]')`),null);
 await evaluate(manager,`document.querySelector('[name=supplier_id]').add(new Option('Inactive fixture','901'))`);
 await submit(manager,{supplier_id:'901'},`document.body.textContent.includes('invalid or inactive')`);
 await shot(manager,'inactive-supplier-rejected');
 await submit(manager,{supplier_id:'900',expected_delivery_date:'2026-12-01',notes:long},`location.pathname==='/procurement/orders'`);
 const po=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);
 await state(po,'order-draft');
 await navigate(manager,po);const cost=await evaluate(manager,`document.querySelector('main a[href$="/edit-cost"]').getAttribute('href')`);
 await review(manager,cost,'order-edit-cost');await submit(manager,{unit_cost:'2.50'},`location.pathname===${JSON.stringify(po)}`);
 assert(await evaluate(manager,`document.querySelector('tfoot').textContent.includes('25.63')`));
 await send('Page.navigate',{url:new URL(primary+'/create-order',await evaluate(manager,'location.origin')).href},manager);await until(manager,`location.pathname===${JSON.stringify(po)}&&document.readyState==='complete'`);
 await navigate(manager,po);await action(manager,'/send',`document.body.textContent.includes('Sent')`);
 await state(po,'order-sent',[['manager',manager],['viewer',viewer]]);
 // Existing orders remain receivable when their supplier becomes inactive.
 await evaluate(operator,`(async()=>{await fetch('/procurement/suppliers/900/status',{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name=csrf-token]').content})})})()`);
 const receive='/procurement/receipts/'+po.split('/').at(-1)+'/receive';
 await review(manager,receive,'receive-sent');
 await navigate(manager,receive);
 const token=await evaluate(manager,`document.querySelector('[name=submission_id]').value`);
 const qty=await evaluate(manager,`document.querySelector('[name^=quantity_received_]').name`);
 await submit(manager,{warehouse_id:'',notes:long,[qty]:'4.25'},`document.body.textContent.includes('Receiving warehouse is required.')`,true);
 assert.equal(await evaluate(manager,`document.querySelector('[name=submission_id]').value`),token);
 await shot(manager,'receive-validation');
 const replay=await evaluate(manager,`(()=>{const f=document.querySelector('main form');f.warehouse_id.value='900';f.elements.namedItem(${JSON.stringify(qty)}).value='4.25';return [...new FormData(f).entries()]})()`);
 await submit(manager,{warehouse_id:'900',[qty]:'4.25',notes:long},`location.pathname.startsWith('/procurement/receipts/')&&Number(location.pathname.split('/').at(-1))>0`);
 const receipt=await evaluate(manager,'location.pathname');await state(receipt,'receipt-historical');
 const replayPath=await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(receive)},{method:'POST',body:new URLSearchParams(${JSON.stringify(replay)})});return new URL(r.url).pathname})()`);assert.equal(replayPath,receipt);
 await state(po,'order-partial');
 await review(manager,receive,'receive-partial');
 assert.equal(await evaluate(manager,`document.querySelector('[name^=quantity_received_]').max`),'6.00');
 assert.notEqual(await evaluate(manager,`document.querySelector('[name=submission_id]').value`),token);
 await review(viewer,'/procurement/receipts/history','receipt-history');
 const print=viewer;await navigate(print,po+'/print');
 assert.equal(await evaluate(print,`document.querySelector('#erp-navigation')`),null);
 assert(await evaluate(print,`document.body.textContent.includes('25.63')&&!document.querySelector('img[src=x]')`));
 await send('Emulation.setEmulatedMedia',{media:'print'},print);
 const pdf=await send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true},print);fs.writeFileSync(path.join(artifacts,'purchase-order-a4.pdf'),Buffer.from(pdf.data,'base64'));
 await shot(print,'purchase-order-print');await send('Emulation.setEmulatedMedia',{media:''},print);
 await navigate(manager,receive);await submit(manager,{warehouse_id:'900',[qty]:'6.00',notes:'Final delivery'},`location.pathname.startsWith('/procurement/receipts/')&&Number(location.pathname.split('/').at(-1))>0`);
 await state(po,'order-received',[['manager',manager],['viewer',viewer]]);
 await review(viewer,primary,'request-completed');
 await send('Page.navigate',{url:new URL(receive,await evaluate(manager,'location.origin')).href},manager);await until(manager,`location.pathname==='/procurement/receipts'&&document.readyState==='complete'`);
 // A separately rejected request preserves the reason and approval-only controls.
 const rejected=await create('GUI rejected request');await add(rejected);await navigate(manager,rejected);await action(manager,'/submit',`document.body.textContent.includes('submitted successfully.')`);
 await review(approver,rejected+'/reject','request-reject');await submit(approver,{rejection_reason:long},`location.pathname===${JSON.stringify(rejected)}`);await state(rejected,'request-rejected');
 // Cancellation remains a confirmed operation on an unreceived order.
 const cancelled=await create('GUI cancelled order');await add(cancelled);await navigate(manager,cancelled);await action(manager,'/submit',`document.body.textContent.includes('submitted successfully.')`);await navigate(approver,cancelled);await action(approver,'/approve',`document.body.textContent.includes('approved successfully.')`);
 // Activate the synthetic supplier for the new order, then leave history intact.
 await evaluate(operator,`(async()=>{await fetch('/procurement/suppliers/900/status',{method:'POST',body:new URLSearchParams({is_active:'1',csrf_token:document.querySelector('meta[name=csrf-token]').content})})})()`);
 await navigate(manager,cancelled+'/create-order');await submit(manager,{supplier_id:'900'},`location.pathname==='/procurement/orders'`);
 const cancelledPo=await evaluate(manager,`document.querySelector('main tbody a').getAttribute('href')`);await navigate(manager,cancelledPo);await action(manager,'/cancel',`document.body.textContent.includes('Cancelled')`);await review(viewer,cancelledPo,'order-cancelled');
 for(const url of ['/procurement/requests','/procurement/orders','/procurement/receipts'])await state(url,'populated-'+url.split('/').at(-1));
 // Denied actions and CSRF remain enforced independently of hidden buttons.
 await navigate(viewer,primary);const deny=await evaluate(viewer,`(async()=>{const r=await fetch(${JSON.stringify(primary+'/approve')},{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name=csrf-token]').content})});return new URL(r.url).pathname})()`);assert.equal(deny,'/dashboard');
 await navigate(manager,po);assert.equal(await evaluate(manager,`(async()=>{const r=await fetch(${JSON.stringify(po+'/cancel')},{method:'POST',body:new URLSearchParams({csrf_token:'invalid'})});return r.status})()`),400);
 assert.equal(errors.length,0,JSON.stringify(errors));assert(dialogs.some(x=>x.includes('Save this goods receipt')));
 console.log('PASS Chrome Procurement: manager/approver/viewer at 1440/1024/768/390/320; native PR item CRUD/submit/approve/reject, inactive supplier rejection/duplicate PO, cost/totals/send/cancel, partial/final receipt with token retention/replay, inactive-supplier historical receiving, permissions/CSRF, escaped long values and A4 PDF');
};
