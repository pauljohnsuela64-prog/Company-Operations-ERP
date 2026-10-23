// Bounded automated semantics/keyboard checks; no WCAG or screen-reader certification.
const assert = require('node:assert/strict');
module.exports = async ({send, tab, evaluate, navigate, until}) => {
  const version = await send('Browser.getVersion');
  console.log('RELEASE browser version:', version.product, version.userAgent);
  const {browserContextId} = await send('Target.createBrowserContext');
  const manager = await tab(browserContextId);
  await navigate(manager, '/login');
  await evaluate(manager, "(()=>{const f=document.querySelector('form');f.username.value='review-user';f.password.value='review-password';f.requestSubmit();})()");
  await until(manager, "location.pathname==='/dashboard' && document.readyState==='complete'");
  const routes = ['/inventory/items','/inventory/warehouses','/procurement/requests',
    '/finance/expenses','/employees','/attendance','/leave/requests','/payroll/periods',
    '/it/assets','/it/help-desk','/admin/audit-logs'];
  let pages = 0, controls = 0;
  for (const width of [1440,1024,768,390,320]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false},manager);
    for (const route of routes) {
      await navigate(manager, route);
      assert.equal(await evaluate(manager, 'document.documentElement.scrollWidth>innerWidth'),false,route+' overflow');
      const {nodes} = await send('Accessibility.getFullAXTree',{},manager);
      const visible = nodes.filter(n=>!n.ignored);
      for (const node of visible.filter(n=>['button','textbox','combobox','checkbox','spinbutton'].includes(n.role?.value))) {
        assert(node.name?.value?.trim(), route+' unnamed '+node.role.value);
        controls++;
      }
      assert(visible.some(n=>n.role?.value==='main'), route+' main landmark');
      assert(visible.some(n=>n.role?.value==='heading'&&n.name?.value?.trim()),route+' named heading');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9},manager);
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9},manager);
      const focus = await evaluate(manager, `(()=>{const e=document.activeElement,s=getComputedStyle(e),r=e.getBoundingClientRect();return {tag:e.tagName,visible:r.width>0&&r.height>0,ring:(s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0)||s.boxShadow!=='none'};})()`);
      assert.notEqual(focus.tag,'BODY',route+' keyboard focus');
      assert(focus.visible && focus.ring,route+' visible focus indicator '+JSON.stringify(focus));
      pages++;
    }
  }
  console.log('PASS release automated accessibility:',pages,'pages;',controls,'named controls; AX landmarks/headings, real Tab focus indicators and contained five-width layouts');
};
