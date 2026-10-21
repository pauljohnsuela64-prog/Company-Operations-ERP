const assert = require('node:assert/strict');

module.exports = async ({send, tab, evaluate, navigate, until}) => {
  const context = await send('Target.createBrowserContext');
  const admin = await tab(context.browserContextId);
  await navigate(admin, '/login');
  await evaluate(admin, `(() => {
    document.querySelector('[name=username]').value='review-user';
    document.querySelector('[name=password]').value='review-password';
    document.querySelector('main form, form').requestSubmit();
  })()`);
  await until(admin, `location.pathname==='/dashboard' && document.readyState==='complete'`);
  await navigate(admin, '/admin/users');
  const targetRow = `[...document.querySelectorAll('tbody tr')].find(r=>r.querySelector('td strong')?.textContent.trim()==='admin.browser.target')`;
  const target = await evaluate(admin, `(${targetRow}).querySelector('form[action$="/status"]').getAttribute('action').split('/')[3]`);
  const statusPath = `/admin/users/${target}/status`;
  const rolePath = `/admin/users/${target}/role`;
  assert.equal(await evaluate(admin, `(${targetRow}).querySelector('[name=is_active]').value`), '0');
  const self = `[...document.querySelectorAll('tbody tr')].find(r=>r.querySelector('td strong')?.textContent.trim()==='review-user')`;
  assert.equal(await evaluate(admin, `(${self}).querySelectorAll('form').length`), 0);

  // Submit real rendered controls, retaining old explicit intent for replay.
  await evaluate(admin, `(${targetRow}).querySelector('form[action$="/status"]').requestSubmit()`);
  await until(admin, `location.pathname==='/admin/users' && document.readyState==='complete' && document.body.textContent.includes('deactivated successfully')`);
  assert.equal(await evaluate(admin, `(${targetRow}).querySelector('[name=is_active]').value`), '1');
  async function request(path, fields, validToken=true) {
    return evaluate(admin, `(async()=>{
      const fields=${JSON.stringify(fields)};
      fields.csrf_token=${validToken ? "document.querySelector('meta[name=csrf-token]').content" : "'invalid'"};
      const r=await fetch(${JSON.stringify(path)},{method:'POST',body:new URLSearchParams(fields)});
      return {status:r.status,text:await r.text()};
    })()`);
  }
  const replay = await request(statusPath, {is_active:'0'});
  assert.equal(replay.status,200); // fetch follows the unchanged redirect.
  assert(replay.text.includes('No change made.'));
  assert.equal((await request(statusPath, {})).status,400);
  assert.equal((await request(statusPath, {is_active:'1'},false)).status,400);
  await evaluate(admin, `(${targetRow}).querySelector('form[action$="/status"]').requestSubmit()`);
  await until(admin, `location.pathname==='/admin/users' && document.readyState==='complete' && document.body.textContent.includes('activated successfully')`);
  for (const role of ['6','2']) {
    await evaluate(admin, `(() => {
      const form=(${targetRow}).querySelector('form[action$="/role"]');
      form.elements.role_id.value=${JSON.stringify(role)};
      form.requestSubmit();
    })()`);
    await until(admin, `location.pathname==='/admin/users' && document.readyState==='complete' && document.body.textContent.includes('role updated successfully') && (${targetRow}).querySelector('[name=role_id]').value===${JSON.stringify(role)}`);
    const noChange=await request(rolePath,{role_id:role});
    assert.equal(noChange.status,200);
    assert(noChange.text.includes('No change made.'));
  }
  const last=await request('/admin/users/6/role',{role_id:'2'});
  assert.equal(last.status,409);
  assert(last.text.includes('last active Super Admin'));

  const deniedContext=await send('Target.createBrowserContext');
  const denied=await tab(deniedContext.browserContextId);
  await navigate(denied,'/login');
  await evaluate(denied,`(() => {
    document.querySelector('[name=username]').value='denied-user';
    document.querySelector('[name=password]').value='review-password';
    document.querySelector('main form, form').requestSubmit();
  })()`);
  await until(denied,`location.pathname==='/dashboard' && document.readyState==='complete'`);
  const forged=await evaluate(denied,`(async()=>{
    const r=await fetch(${JSON.stringify(statusPath)},{method:'POST',body:new URLSearchParams({is_active:'0',csrf_token:document.querySelector('meta[name=csrf-token]').content})});
    return {path:new URL(r.url).pathname,text:await r.text()};
  })()`);
  assert.equal(forged.path,'/dashboard');
  assert(forged.text.includes('You do not have permission'));
  console.log('PASS Chrome Administration: native explicit status/role forms, replay/no-op, last-admin protection, self controls, forged permission and CSRF rejection');
};
