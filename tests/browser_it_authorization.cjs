// Real Chrome role matrix. Called only by the disposable MySQL review harness.
const assert = require('node:assert/strict');

module.exports = async function verify({base, controlKey, send, tab, evaluate, navigate, until}) {
  const fixture = await (await fetch(base + '/__review/it-fixture')).json();
  const asset = `/it/assets/${fixture.asset_id}`;
  const ticket = `/it/help-desk/${fixture.ticket_id}`;
  const snapshot = async () => JSON.stringify(await (await fetch(base + '/__review/it-snapshot')).json());
  async function request(t, path, fields = {}, tokenMode = 'valid', extraHeaders = {}) {
    return evaluate(t, `(async () => {
      const fields = ${JSON.stringify(fields)};
      if (${JSON.stringify(path)}.endsWith('/unassign') && fields.assignment_id === undefined)
        fields.assignment_id = document.querySelector('main input[name="assignment_id"]')?.value || '';
      if (${JSON.stringify(tokenMode)} === 'valid') fields.csrf_token = document.querySelector('meta[name="csrf-token"]').content;
      if (${JSON.stringify(tokenMode)} === 'invalid') fields.csrf_token = 'forged';
      const response = await fetch(${JSON.stringify(path)}, {method:'POST', body:new URLSearchParams(fields), headers:${JSON.stringify(extraHeaders)}});
      return {status:response.status, path:new URL(response.url).pathname, text:await response.text()};
    })()`);
  }
  async function login(username) {
    const {browserContextId} = await send('Target.createBrowserContext');
    const t = await tab(browserContextId);
    await navigate(t, '/login');
    await evaluate(t, `(() => {
      document.querySelector('[name="username"]').value = ${JSON.stringify(username)};
      document.querySelector('[name="password"]').value = 'review-password';
      document.querySelector('form').requestSubmit();
    })()`);
    await until(t, `location.pathname === '/dashboard' && document.readyState === 'complete'`);
    assert(!(await evaluate(t, `document.body.textContent.includes('Internal Server Error')`)));
    return t;
  }
  async function nav(t, allowed, denied) {
    await navigate(t, '/dashboard');
    const state = await evaluate(t, `({asset:!!document.querySelector('#erp-navigation a[href="/it/assets"]'), help:!!document.querySelector('#erp-navigation a[href="/it/help-desk"]'), cards:[...document.querySelectorAll('main a')].map(a=>a.getAttribute('href'))})`);
    assert.equal(state.asset, allowed.includes('asset'));
    assert.equal(state.help, allowed.includes('help'));
    for (const [name, path] of [['asset', '/it/assets'], ['help', '/it/help-desk']]) {
      assert.equal(state.cards.includes(path), allowed.includes(name));
    }
    if (denied) {
      const path = denied === 'asset' ? '/it/assets' : '/it/help-desk';
      const result = await evaluate(t, `(async()=>{const r=await fetch(${JSON.stringify(path)});return new URL(r.url).pathname;})()`);
      assert.equal(result, '/dashboard');
    }
  }
  async function noMutationControls(t, path) {
    await navigate(t, path);
    const actions = await evaluate(t, `({forms:[...document.querySelectorAll('main form')].filter(f=>f.method.toUpperCase()==='POST').length,
      links:[...document.querySelectorAll('main a')].map(a=>a.getAttribute('href')).filter(h=>h && /\\/(add|edit)(?:$|[?])/.test(h))})`);
    assert.equal(actions.forms, 0, path);
    assert.deepEqual(actions.links, [], path);
  }
  async function hasForm(t, path, action) {
    await navigate(t, path);
    assert(await evaluate(t, `!!document.querySelector('main form[action="${action}"]')`), action);
  }

  const assetViewer = await login('asset-viewer');
  const helpViewer = await login('helpdesk-viewer');
  for (const [t, module, paths] of [
    [assetViewer, 'asset', ['/it/assets', asset, '/it/assets/categories', '/it/assets/reports']],
    [helpViewer, 'help', ['/it/help-desk', ticket, '/it/help-desk/reports']]
  ]) {
    await nav(t, [module], module === 'asset' ? 'help' : 'asset');
    for (const path of paths) await noMutationControls(t, path);
    const before = await snapshot();
    for (const [path, methods] of fixture.routes) {
      if (!methods.includes('POST')) continue;
      const result = await request(t, path, {employee_id:'1', assigned_to:'5', resolution:'Forged'});
      assert.equal(result.path, '/dashboard', path);
      assert.equal(result.status, 200);
    }
    assert.equal(await snapshot(), before);
  }
  console.log('PASS Chrome Asset Viewer and Help Desk Viewer: independent navigation/cards/read pages, hidden controls, all 17 forged POST denials with unchanged database snapshot');

  const manager = await login('it-manager');
  const admin = await login('super-admin');
  for (const t of [manager, admin]) {
    await nav(t, ['asset', 'help']);
    for (const [path, action] of [['/it/assets', '/it/assets/add'], ['/it/assets/categories', '/it/assets/categories/add'], ['/it/help-desk', '/it/help-desk/add']]) {
      await navigate(t, path);
      assert(await evaluate(t, `!!document.querySelector('main a[href="${action}"]')`), action);
    }
    await hasForm(t, asset, asset + '/assign');
    await hasForm(t, ticket, ticket + '/assign');
    const before = await snapshot();
    for (const [path, methods] of fixture.routes) {
      if (!methods.includes('POST')) continue;
      for (const mode of ['missing', 'invalid']) {
        assert.equal((await request(t, path, {}, mode)).status, 400, path);
      }
    }
    assert.equal(await snapshot(), before);
    // These fetches originate in the real page and retain its cookie and CSRF token.
    assert.equal((await request(t, asset + '/assign', {employee_id:'1'})).path, asset);
    await hasForm(t, asset, asset + '/unassign');
    assert.equal((await request(t, asset + '/unassign')).path, asset);
    await hasForm(t, asset, asset + '/assign');
    assert.equal((await request(t, ticket + '/assign', {assigned_to:'5'})).path, ticket);
    await hasForm(t, ticket, ticket + '/start');
  }
  console.log('PASS Chrome IT Manager and Super Admin: management links/forms, persisted asset assign/return and ticket assignment, all 17 routes reject missing/invalid CSRF');

  // Approved policy: stale Return forms cannot clear LOST/MAINTENANCE custody.
  for (const status of ['LOST', 'MAINTENANCE']) {
    assert.equal((await request(manager, asset + '/assign', {employee_id:'1'})).path, asset);
    await hasForm(manager, asset, asset + '/unassign');
    const assignment_id = await evaluate(manager, `document.querySelector('main input[name="assignment_id"]').value`);
    if (status === 'LOST') {
      assert.equal((await request(manager, asset + '/lost')).path, asset);
    } else {
      assert.equal((await request(manager, asset + '/maintenance/add', {
        maintenance_type:'Repair', description:'Synthetic browser policy check', start_date:'2026-10-01'
      })).path, asset);
    }
    await navigate(manager, asset);
    assert.equal(await evaluate(manager, `Boolean(document.querySelector('main form[action="${asset}/unassign"]'))`), false);
    const before = await snapshot();
    const rejected = await request(manager, asset + '/unassign', {assignment_id});
    assert(rejected.text.includes(status === 'LOST' ? 'Recover this asset before returning it.' : 'Complete maintenance before returning this asset.'));
    assert.equal(await snapshot(), before);
    if (status === 'LOST') {
      assert.equal((await request(manager, asset + '/restore')).path, asset);
    } else {
      const completion = await evaluate(manager, `document.querySelector('main form[action$="/complete"]').getAttribute('action')`);
      assert.equal((await request(manager, completion, {completed_date:'2026-10-02'})).path, asset);
    }
    await hasForm(manager, asset, asset + '/unassign');
    assert.equal(await evaluate(manager, `document.querySelector('main input[name="assignment_id"]').value`), assignment_id);
    assert.equal((await request(manager, asset + '/unassign')).path, asset);
    await hasForm(manager, asset, asset + '/assign');
  }
  console.log('PASS Chrome LOST/MAINTENANCE return controls hidden, stale POST rejected without history changes, recovery/completion then legitimate return');

  await require('./browser_it_asset_validation.cjs')({manager, navigate, evaluate, until, request, snapshot});

  const auditor = await login('review-user');
  await navigate(auditor, '/admin/audit-logs?module=IT_ASSETS');
  const auditText = await evaluate(auditor, `document.querySelector('main table').textContent`);
  for (const value of ['IT_ASSETS', 'IT_ASSET', 'BROWSER-ASSET', 'ASSIGN', 'RETURN', 'MARK_LOST', 'RECOVER', 'COMPLETE']) {
    assert(auditText.includes(value), `Central IT audit page missing ${value}`);
  }
  console.log('PASS Chrome central Audit Logs: IT module filter, asset identity and committed lifecycle/maintenance actions visible');

  assert.equal((await request(manager, ticket + '/start')).path, ticket);
  await hasForm(manager, ticket, ticket + '/resolve');
  assert.equal((await request(manager, ticket + '/resolve', {resolution:'Browser fixed'})).path, ticket);
  await hasForm(admin, ticket, ticket + '/close');
  assert.equal((await request(admin, ticket + '/close')).path, ticket);
  await navigate(admin, ticket);
  assert(await evaluate(admin, `document.body.textContent.includes('Browser fixed')`));

  // Change fixed synthetic DB targets using test-only helpers, never application routes.
  assert.equal((await request(admin, '/__review/it-control', {action:'revoke'}, 'valid', {'X-Review-Key':controlKey})).status, 200);
  const before = await snapshot();
  for (const [path, methods] of fixture.routes) {
    if (methods.includes('POST')) assert.equal((await request(manager, path)).path, '/dashboard', path);
  }
  await noMutationControls(manager, asset);
  await noMutationControls(manager, ticket);
  assert.equal(await snapshot(), before);
  assert.equal((await request(admin, '/__review/it-control', {action:'disable'}, 'valid', {'X-Review-Key':controlKey})).status, 200);
  assert.equal((await request(manager, asset + '/retire')).path, '/login');
  const nextPath = await evaluate(manager, `(async()=>{const r=await fetch('/it/help-desk');return new URL(r.url).pathname;})()`);
  assert.equal(nextPath, '/login');
  assert.equal(await snapshot(), before);
  console.log('PASS Chrome ticket start/resolve/close, same-session management revocation (all 17 routes), hidden buttons after revocation and disabled-account denial');
};
