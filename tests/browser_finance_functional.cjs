// Finance corrections on a disposable instance, using the existing CDP driver.
const assert = require('node:assert/strict');

module.exports = async function ({send, tab, evaluate, navigate, until, submit, fixture}) {
  async function login(username) {
    const t = await tab((await send('Target.createBrowserContext')).browserContextId);
    await navigate(t, '/login');
    await submit(t, {username, password:'review-password'});
    await until(t, `location.pathname === '/dashboard' && document.readyState === 'complete'`);
    return t;
  }
  const manager = await login('review-user');
  const viewer = await login('asset-viewer');
  const form = {expense_date:'2026-12-31', category_id:String(fixture.category),
    department_id:String(fixture.department), supplier_id:String(fixture.supplier),
    purchase_order_id:String(fixture.po), payment_method:'CARD',
    description:'Finance correction browser', amount:'0', reference_number:'FORM-REF', notes:'Retained notes'};
  await navigate(manager, '/finance/expenses/add');
  // Bypass only HTML5 validation for this deliberately invalid submission.
  // The native POST still carries genuine CSRF and hits unchanged server validation.
  await evaluate(manager, `(() => {const f=document.querySelector('main form');
    for(const [name,value] of Object.entries(${JSON.stringify(form)}))f.elements.namedItem(name).value=value;
    HTMLFormElement.prototype.submit.call(f);})()`);
  await until(manager, `document.body.textContent.includes('Amount must be greater than zero') && document.readyState === 'complete'`);
  const retained = await evaluate(manager, `Object.fromEntries([...document.querySelector('main form').elements].filter(e=>e.name&&e.name!=='csrf_token').map(e=>[e.name,e.value]))`);
  for (const [name,value] of Object.entries(form)) assert.equal(retained[name],value,name);
  await submit(manager, {amount:'0.20'});
  await until(manager, `location.pathname === '/finance/expenses' && document.readyState === 'complete'`);
  const id = await evaluate(manager, `Number([...document.querySelectorAll('tr')].find(r=>r.textContent.includes('Finance correction browser')).querySelector('a[href*="/finance/expenses/"]').getAttribute('href').split('/').at(-1))`);
  await navigate(manager, `/finance/expenses/${id}/edit`);
  await evaluate(manager, `(() => {const f=document.querySelector('main form');f.elements.amount.value='0';f.elements.payment_method.value='CHECK';HTMLFormElement.prototype.submit.call(f);})()`);
  await until(manager, `document.body.textContent.includes('Amount must be greater than zero') && document.readyState === 'complete'`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="department_id"]').value`),String(fixture.department));
  assert.equal(await evaluate(manager, `document.querySelector('[name="payment_method"]').value`),'CHECK');
  await submit(manager, {amount:'0.30'});
  await until(manager, `location.pathname === '/finance/expenses/${id}' && document.readyState === 'complete'`);
  console.log('PASS Chrome Add/Edit failed validation retains all fields; native correction commits the intended department/supplier/PO/payment method');

  for (const year of [2026,2010,2027,1000,9999]) {
    await navigate(manager, `/finance/budgets?year=${year}&department_id=${fixture.department}`);
    assert.equal(await evaluate(manager, `document.querySelector('[name="year"]').value`),String(year));
    await evaluate(manager, `window.financeApplyPending = true`);
    await submit(manager, {});
    await until(manager, `typeof window.financeApplyPending === 'undefined' && document.readyState === 'complete' && location.search.includes('year=${year}')`);
    assert.equal(await evaluate(manager, `document.querySelector('[name="year"]').value`),String(year));
    assert.equal(await evaluate(manager, `document.querySelector('[name="department_id"]').value`),String(fixture.department));
  }
  // Invalid Budget years fail without silently replacing the requested year.
  await send('Page.navigate', {url:fixture.base+'/finance/budgets?year=NaN&department_id='+fixture.department}, manager);
  await until(manager, `document.body.textContent.includes('Budget year must be between') && document.readyState === 'complete'`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="department_id"]').value`),String(fixture.department));
  for (const [year,label] of [[2024,'Warning'],[2025,'Fully Used'],[2026,'Over Budget']]) {
    await navigate(manager, `/finance/budgets?year=${year}&department_id=${fixture.department}`);
    assert(await evaluate(manager, `document.querySelector('main tbody').textContent.includes(${JSON.stringify(label)})`));
    assert(await evaluate(manager, `document.querySelector('main tbody').textContent.includes('100.0%')`));
  }
  const budgetPath = '/finance/budgets?year=2025&department_id='+fixture.department;
  await navigate(viewer,budgetPath);
  assert.equal(await evaluate(viewer, `Boolean(document.querySelector('main a[href="/finance/budgets/add"],main a[href$="/edit"]'))`),false);
  assert(await evaluate(viewer, `Boolean(document.querySelector('main a[href="/finance/budgets/${fixture.budget}"]'))`));
  await navigate(viewer, `/finance/budgets/${fixture.budget}`);
  const denial = await evaluate(viewer, `(async()=>{const csrf_token=document.querySelector('meta[name="csrf-token"]').content;
    const r=await fetch('/finance/budgets/add',{method:'POST',body:new URLSearchParams({csrf_token,department_id:'${fixture.department}',budget_year:'2029',budget_amount:'1'})});return new URL(r.url).pathname;})()`);
  assert.equal(denial,'/dashboard');
  await navigate(manager,budgetPath);
  assert(await evaluate(manager, `Boolean(document.querySelector('main a[href="/finance/budgets/add"]')) && Boolean(document.querySelector('main a[href="/finance/budgets/${fixture.budget}/edit"]'))`));
  console.log('PASS Chrome valid years persist through native Apply; malformed year feedback, exact usage labels, viewer/manager links and forged POST denial');
  await require('./browser_budget_management.cjs')({manager,viewer,evaluate,navigate,until,submit,fixture});
};
