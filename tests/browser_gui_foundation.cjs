// Runs only against the verified disposable server and synthetic accounts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
module.exports = async ({send,tab,evaluate,navigate,until,errors,artifacts}) => {
  async function login(username) {
    const {browserContextId}=await send('Target.createBrowserContext');
    const t=await tab(browserContextId);
    await navigate(t,'/login');
    await evaluate(t,`(() => {
      document.querySelector('[name=username]').value=${JSON.stringify(username)};
      document.querySelector('[name=password]').value='review-password';
      document.querySelector('form').requestSubmit();
    })()`);
    await until(t,`location.pathname==='/dashboard' && document.readyState==='complete'`);
    return t;
  }
  async function shot(t,name,full=true) {
    const {contentSize}=await send('Page.getLayoutMetrics',{},t);
    // Full-page capture hides scrollbars; use innerWidth so that this does not
    // crop the right-hand gutter when Chrome lays out that larger surface.
    const width=await evaluate(t,'innerWidth');
    const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:full,...(full?{clip:{x:0,y:0,width,height:contentSize.height,scale:1}}:{})},t);
    fs.writeFileSync(path.join(artifacts,name+'.png'),Buffer.from(data,'base64'));
  }
  async function layout(t,width) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false},t);
    await until(t,`innerWidth===${width}`);
    await evaluate(t,`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    assert(await evaluate(t,`Boolean(document.querySelector('link[href*=bootstrap]').sheet) && getComputedStyle(document.body).boxSizing==='border-box'`));
    const overflow=await evaluate(t,`document.documentElement.scrollWidth > document.documentElement.clientWidth`);
    assert.equal(overflow,false,`horizontal overflow at ${width}`);
    assert(await evaluate(t,`[...document.querySelectorAll('.kpi-panel')].every(e=>e.getBoundingClientRect().width>0)`));
    const panels=await evaluate(t,`[...document.querySelectorAll('.kpi-panel')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})`);
    panels.forEach((a,i)=>panels.slice(i+1).forEach(b=>assert(!(a.x<b.x+b.w-1&&a.x+a.w>b.x+1&&a.y<b.y+b.h-1&&a.y+a.h>b.y+1),'overlapping KPI panels')));
  }
  const operator=await login('review-user');
  const hr=await login('hr.dashboard');
  const denied=await login('denied-user');
  for(const [role,t] of [['operator',operator],['hr',hr],['no-modules',denied]]) {
    for(const width of [1440,1024,768,390,320]) {
      await layout(t,width);
      assert.equal(await evaluate(t,`document.querySelectorAll('h1').length`),1);
      assert(await evaluate(t,`Boolean(document.querySelector('form.logout-form [name=csrf_token]'))`));
      if(role==='hr') {
        assert.equal(await evaluate(t,`[...document.querySelectorAll('.kpi-panel')].map(e=>e.dataset.section).join(',')`),'employees,attendance,leave');
        assert.equal(await evaluate(t,`document.querySelectorAll('#nav-admin, #nav-finance').length`),0);
      }
      if(role==='operator') {
        assert.equal(await evaluate(t,`document.querySelectorAll('.kpi-panel').length`),9);
        assert(await evaluate(t,`Boolean(document.querySelector('[data-section=payroll].is-unavailable'))`));
      }
      if(role==='no-modules') assert(await evaluate(t,`Boolean(document.querySelector('.dashboard-empty'))`));
      if(width<768) {
        assert(await evaluate(t,`document.querySelector('#erp-navigation').hidden`));
        await evaluate(t,`document.querySelector('.navigation-toggle').click()`);
        assert(await evaluate(t,`!document.querySelector('#erp-navigation').hidden`));
      }
      const group=role==='no-modules'?null:'#nav-hr summary';
      if(group) {
        await evaluate(t,`document.querySelector(${JSON.stringify(group)}).focus()`);
        await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40},t);
        await until(t,`document.querySelector('#nav-hr').open`);
        const bounds=await evaluate(t,`(()=>{const r=document.querySelector('#nav-panel-hr').getBoundingClientRect();return {left:r.left,right:r.right}})()`);
        assert(bounds.left>=0&&bounds.right<=width,`dropdown outside viewport ${width}`);
        await shot(t,`${role}-${width}-navigation`,false);
        await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27},t);
        assert(await evaluate(t,`document.activeElement===document.querySelector('#nav-hr summary')`));
      }
      if(width<768) await evaluate(t,`document.querySelector('.navigation-toggle').click()`);
      await shot(t,`${role}-${width}`);
    }
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false},operator);
  await navigate(operator,'/dashboard?__gui_fixture=zero');
  assert.equal(await evaluate(operator,`document.querySelectorAll('.kpi-primary strong').length`),9);
  assert(await evaluate(operator,`[...document.querySelectorAll('.kpi-primary strong')].every(e=>e.textContent==='0')`));
  assert.equal(await evaluate(operator,`document.querySelectorAll('.is-unavailable').length`),0);
  assert(await evaluate(operator,`document.body.textContent.includes('No paid payroll period yet.')`));
  await shot(operator,'operator-zero-1440');
  await layout(operator,390);await shot(operator,'operator-zero-390');
  // Native keyboard skip link and visible focus; no replacement navigation engine.
  await evaluate(hr,`document.querySelector('.skip-link').focus()`);
  assert(await evaluate(hr,`document.querySelector('.skip-link').getBoundingClientRect().top>=0`));
  assert.equal(errors.length,0,`uncaught JavaScript errors: ${errors}`);
  console.log('PASS GUI Chrome: operator, HR Manager, no-permission account at 1440/1024/768/390/320; Bootstrap loaded, no overflow/overlap, native dropdown keyboard/Escape/mobile menu, zero/unavailable/empty states, skip focus, CSRF fields and no uncaught JavaScript exceptions');
};
