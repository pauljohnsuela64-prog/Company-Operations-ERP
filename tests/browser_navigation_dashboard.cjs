const assert = require('node:assert/strict');
module.exports = async ({send,tab,evaluate,navigate,until}) => {
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
  const hr=await login('hr.dashboard');
  for(const path of ['/attendance','/leave/requests']) {
    assert(await evaluate(hr,`Boolean(document.querySelector('#erp-navigation a[href="${path}"]'))`));
  }
  assert.equal(await evaluate(hr,`document.querySelectorAll('#nav-admin, #erp-navigation a[href^="/payroll"]').length`),0);
  assert.equal(await evaluate(hr,`document.body.textContent.includes('Currently unavailable.')`),false);
  for(const path of ['/attendance','/leave/requests']) {
    await evaluate(hr,`(() => {
      document.querySelector('#nav-hr').open=true;
      document.querySelector('#erp-navigation a[href="${path}"]').click();
    })()`);
    await until(hr,`location.pathname==='${path}' && document.readyState==='complete'`);
    assert(await evaluate(hr,`Boolean(document.querySelector('#erp-navigation a[href="${path}"][aria-current=page]'))`));
    assert(await evaluate(hr,`document.querySelector('[aria-label=Breadcrumb]').textContent.includes('Human Resources')`));
  }
  await navigate(hr,'/dashboard');
  const forged=await evaluate(hr,`(async()=>{
    const r=await fetch('/admin/users/1/status',{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name=csrf-token]').content})});
    return {path:new URL(r.url).pathname,text:await r.text()};
  })()`);
  assert.equal(forged.path,'/dashboard');
  assert(forged.text.includes('You do not have permission'));
  const operator=await login('review-user');
  assert(await evaluate(operator,`document.body.textContent.includes('Currently unavailable.')`));
  assert.equal(await evaluate(operator,`document.body.textContent.includes('No paid payroll period yet.')`),false);
  assert.equal(await evaluate(operator,`document.body.textContent.includes('dashboard_browser_saved_payroll')`),false);
  assert.equal(await evaluate(operator,`document.querySelectorAll('#erp-navigation .nav-dropdown').length`),6);
  assert(await evaluate(hr,`Boolean(document.querySelector('form.logout-form [name=csrf_token]'))`));
  console.log('PASS Chrome HR Manager without Administration grants: native Attendance/Leave navigation, active/breadcrumb states, denied Administration POST and no Payroll unavailable card; authorized operator sees explicit unavailable Payroll');
};
