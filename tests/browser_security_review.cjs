// Dependency-free Chrome DevTools Protocol checks against an isolated test server.
const [base, debugPort] = process.argv.slice(2);
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const keepAlive = setInterval(() => {}, 1000);
(async () => {
  const version = await (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).json();
  console.log('Browser:', version.Browser);
  const socket = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let serial = 0;
  const waiting = new Map();
  socket.onclose = () => { for (const pending of waiting.values()) pending.reject(new Error('Browser CDP socket closed')); };
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const pending = waiting.get(message.id);
    if (!pending) return;
    waiting.delete(message.id);
    message.error ? pending.reject(new Error(JSON.stringify(message.error))) : pending.resolve(message.result);
  };
  function send(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++serial;
      const timeout = setTimeout(() => { waiting.delete(id); reject(new Error(`CDP command timed out: ${method}`)); }, 10000);
      waiting.set(id, {resolve: value => { clearTimeout(timeout); resolve(value); }, reject: error => { clearTimeout(timeout); reject(error); }});
      socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  async function tab() {
    const {targetId} = await send('Target.createTarget', {url:'about:blank'});
    const {sessionId} = await send('Target.attachToTarget', {targetId, flatten:true});
    await send('Page.enable', {}, sessionId);
    await send('Network.enable', {}, sessionId);
    // The review uses only local resources, never external sites or company hosts.
    await send('Network.setBlockedURLs', {urls:['https://*']}, sessionId);
    return sessionId;
  }
  async function evaluate(tab, expression) {
    const result = await send('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true}, tab);
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function until(tab, expression) {
    for (let i = 0; i < 120; i++) {
      try { if (await evaluate(tab, expression)) return; } catch {}
      await delay(100);
    }
    throw new Error(`Browser condition timed out: ${expression}`);
  }
  async function navigate(tab, path) {
    await send('Page.navigate', {url:base+path}, tab);
    await until(tab, `location.href === ${JSON.stringify(base+path)} && document.readyState === 'complete'`);
  }
  async function submit(tab, values, options={}) {
    await evaluate(tab, `(() => {
      const forms = [...document.querySelectorAll('form')];
      const form = forms.find(f => !f.classList.contains('logout-form'));
      for (const [name,value] of Object.entries(${JSON.stringify(values)})) form.elements.namedItem(name).value=value;
      if (${Boolean(options.removeToken)}) form.querySelector('[name="csrf_token"]').remove();
      form.requestSubmit();
    })()`);
  }
  let first;
  try {
    first = await tab();
    await navigate(first, '/login');
    await submit(first, {username:'review-user',password:'review-password'}, {removeToken:true});
    await until(first, `document.body.textContent.includes('Submission not processed')`);
    await navigate(first, '/login');
    await submit(first, {username:'review-user',password:'wrong-password'});
    await until(first, `document.body.textContent.includes('Invalid username or password.')`);
    assert(await evaluate(first, `Boolean(document.querySelector('input[name="csrf_token"]'))`));
    await submit(first, {username:'review-user',password:'review-password'});
    await until(first, `location.pathname === '/dashboard' && document.readyState === 'complete'`);
    assert(!(await evaluate(first, `document.body.textContent.includes('Internal Server Error')`)));
    console.log('PASS real Chrome login: missing-token rejection, validation error, then valid rendered form');

    const second = await tab();
    await navigate(first, '/procurement/suppliers/add');
    await navigate(second, '/procurement/suppliers/add');
    await submit(first, {supplier_code:'BROWSER-A',supplier_name:'Browser supplier A'});
    await until(first, `location.pathname === '/procurement/suppliers' && document.readyState === 'complete'`);
    await submit(second, {supplier_code:'BROWSER-B',supplier_name:'Browser supplier B'});
    await until(second, `location.pathname === '/procurement/suppliers' && document.readyState === 'complete'`);
    const cookies = (await send('Network.getCookies', {urls:[base]}, first)).cookies;
    const sessionCookie = cookies.find(cookie => cookie.name === 'session');
    assert.equal(sessionCookie.httpOnly, true);
    assert.equal(sessionCookie.sameSite, 'Lax');
    assert.equal(sessionCookie.secure, false);
    assert(!(await evaluate(first, `document.cookie.includes('session=')`)));
    console.log('PASS real Chrome two tabs and HTTP cookie attributes: HttpOnly and SameSite=Lax');

    await navigate(first, '/procurement/suppliers/add');
    const old = await evaluate(first, `(async () => (await (await fetch('/__review/expired-token')).json()).csrf_token)()`);
    await evaluate(first, `document.querySelector('main form input[name="csrf_token"]').value=${JSON.stringify(old)}`);
    await submit(first, {supplier_code:'BROWSER-C',supplier_name:'Browser supplier C'});
    await until(first, `document.body.textContent.includes('Submission not processed')`);
    assert(await evaluate(first, `document.body.textContent.includes('Resubmit reviewed values')`));
    assert.equal(await evaluate(first, `(async () => (await (await fetch('/__review/supplier-count?code=BROWSER-C')).json()).count)()`), 0);
    await evaluate(first, `document.querySelector('main form button[type="submit"]').click()`);
    await until(first, `location.pathname === '/procurement/suppliers' && document.readyState === 'complete'`);
    assert.equal(await evaluate(first, `(async () => (await (await fetch('/__review/supplier-count?code=BROWSER-C')).json()).count)()`), 1);
    console.log('PASS real Chrome expired form: no automatic write, explicit renewed form submits original values once');

    await navigate(first, '/procurement/suppliers/add');
    await submit(first, {supplier_code:'BROWSER-C',supplier_name:'Browser supplier C'});
    await until(first, `document.body.textContent.includes('Supplier code already exists.')`);
    assert(await evaluate(first, `Boolean(document.querySelector('main form input[name="csrf_token"]'))`));
    await navigate(first, '/logout');
    await navigate(second, '/procurement/suppliers/add');
    assert(await evaluate(second, `Boolean(document.querySelector('input[name="supplier_code"]'))`));
    await evaluate(first, `document.querySelector('main form button[type="submit"]').click()`);
    await until(first, `location.pathname === '/login' && document.readyState === 'complete'`);
    await submit(second, {supplier_code:'BROWSER-D',supplier_name:'Old tab must not write'});
    await until(second, `document.body.textContent.includes('Submission not processed')`);
    console.log('PASS real Chrome validation error, harmless GET logout, protected POST logout, and old-tab rejection');
    console.log('SUCCESS: browser execution used isolated HTTP/MySQL only; production TLS and visual layout not certified');
  } finally {
    await send('Browser.close').catch(() => {});
    socket.close();
  }
})().catch(error => { console.error(error); process.exitCode=1; }).finally(() => clearInterval(keepAlive));
