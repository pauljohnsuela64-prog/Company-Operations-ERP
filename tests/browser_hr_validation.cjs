// Native HR forms against the disposable security-review server only.
const assert = require('node:assert/strict');
module.exports = async ({send, tab, evaluate, navigate, until, fixture}) => {
  async function login(username) {
    const {browserContextId} = await send('Target.createBrowserContext');
    const t = await tab(browserContextId);
    await navigate(t, '/login');
    await evaluate(t, `(() => {
      document.querySelector('[name="username"]').value=${JSON.stringify(username)};
      document.querySelector('[name="password"]').value='review-password';
      document.querySelector('form').requestSubmit();
    })()`);
    await until(t, `location.pathname==='/dashboard' && document.readyState==='complete'`);
    return t;
  }
  const manager = await login('review-user');
  async function submit(values, forged=false) {
    await evaluate(manager, `(() => {
      const f=document.querySelector('main form');
      for(const [k,v] of Object.entries(${JSON.stringify(values)})) {
        const field=f.elements.namedItem(k);
        // Setting a missing select value clears it; add the forged option so
        // the browser actually submits the invalid ID under test.
        if (${forged} && field.tagName==='SELECT' && ![...field.options].some(o=>o.value===v))
          field.add(new Option('Forged test reference',v));
        field.value=v;
      }
      ${forged ? 'HTMLFormElement.prototype.submit.call(f)' : 'f.requestSubmit()'};
    })()`);
  }
  const dept = {department_code:'HR-BROWSER', department_name:'HR browser department', description:'Retained <notes> & details'};
  await navigate(manager, '/departments/add');
  await submit({...dept, description:'X'.repeat(256)}, true);
  await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Description must not exceed 255 characters.')`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="description"]').value`),'X'.repeat(256));
  await submit(dept);
  await until(manager, `location.pathname==='/departments' && document.readyState==='complete'`);
  const deptEdit = await evaluate(manager, `[...document.querySelectorAll('main tr')].find(r=>r.textContent.includes('HR-BROWSER')).querySelector('a[href$="/edit"]').getAttribute('href')`);
  await navigate(manager, deptEdit);
  await submit({...dept, department_code:'X'.repeat(21)}, true);
  await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Department code must not exceed 20 characters.')`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="description"]').value`),dept.description);
  await submit({...dept, description:'Corrected browser department'});
  await until(manager, `location.pathname==='/departments' && document.readyState==='complete'`);
  // Replaying an identical desired state must never toggle the department back.
  for(const desired of ['0','0','1','1']) {
    await navigate(manager, '/departments');
    const response = await evaluate(manager, `(async()=>{
      const token=document.querySelector('meta[name="csrf-token"]').content;
      const r=await fetch(${JSON.stringify(deptEdit.replace('/edit','/status'))},{method:'POST',body:new URLSearchParams({is_active:${JSON.stringify(desired)},csrf_token:token,expected_revision:[...document.querySelectorAll('main tr')].find(r=>r.textContent.includes('HR-BROWSER')).querySelector('[name="expected_revision"]').value})});
      return await r.text();
    })()`);
    assert(response.includes('Department is already in the requested state.') || response.includes(desired==='0' ? 'Department deactivated successfully.' : 'Department activated successfully.'));
  }
  const emp = {employee_number:'HR-BROWSER-EMP', department_id:String(fixture.department), first_name:'Browser', middle_name:'', last_name:'Employee', email:'browser-hr@example.invalid', phone:'', job_title:'Synthetic', hire_date:'2026-01-01'};
  await navigate(manager, '/employees/add');
  await submit({...emp, phone:'P'.repeat(31)}, true);
  await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Phone must not exceed 30 characters.')`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="department_id"]').value`),emp.department_id);
  assert.equal(await evaluate(manager, `document.querySelector('[name="employee_number"]').value`),emp.employee_number);
  await submit(emp);
  await until(manager, `location.pathname==='/employees' && document.readyState==='complete'`);
  const empEdit = await evaluate(manager, `[...document.querySelectorAll('main tr')].find(r=>r.textContent.includes('HR-BROWSER-EMP')).querySelector('a[href$="/edit"]').getAttribute('href')`);
  await navigate(manager, empEdit);
  await submit({...emp, department_id:'999999'},true);
  await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Selected department does not exist.')`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="department_id"]').value`),'999999');
  await submit({...emp,phone:'Corrected phone'});
  await until(manager, `location.pathname==='/employees' && document.readyState==='complete' && document.body.textContent.includes('Employee updated successfully.')`);
  const viewer=await login('hr-viewer');
  for(const path of ['/employees','/departments']) {
    await navigate(viewer,path);
    assert.equal(await evaluate(viewer, `document.querySelectorAll('main form[method="POST"],main a[href$="/add"],main a[href$="/edit"]').length`),0);
  }
  const denied=await evaluate(viewer, `(async()=>{
    const r=await fetch('/employees/add',{method:'POST',body:new URLSearchParams({csrf_token:document.querySelector('meta[name="csrf-token"]').content,employee_number:'FORGED-HR'})});
    return new URL(r.url).pathname;
  })()`);
  assert.equal(denied,'/dashboard');
  console.log('PASS Chrome HR native Add/Edit, server validation, value/selection retention, correction, desired-state replay and viewer restrictions');

  const second = await login('review-user');
  async function saveIn(t, values, forged=false) {
    await evaluate(t, `(() => {
      const f=document.querySelector('main form');
      for(const [key,value] of Object.entries(${JSON.stringify(values)})) f.elements.namedItem(key).value=value;
      ${forged ? 'HTMLFormElement.prototype.submit.call(f)' : 'f.requestSubmit()'};
    })()`);
  }
  await navigate(manager,empEdit);await navigate(second,empEdit);
  const employeeVersion=await evaluate(second, `document.querySelector('[name="expected_revision"]').value`);
  await saveIn(manager,{employment_status:'Resigned'});
  await until(manager, `location.pathname==='/employees' && document.readyState==='complete'`);
  await saveIn(second,{phone:'Stale phone must not persist'});
  await until(second, `document.readyState==='complete' && document.body.textContent.includes('This record changed since you opened the form.')`);
  assert.equal(await evaluate(second, `document.querySelectorAll('main form,main [name="expected_revision"]').length`),0);
  await navigate(second,empEdit);
  assert.equal(await evaluate(second, `document.querySelector('[name="employment_status"]').value`),'Resigned');
  assert.equal(await evaluate(second, `document.querySelector('[name="phone"]').value`),'Corrected phone');
  assert.equal(await evaluate(second, `BigInt(document.querySelector('[name="expected_revision"]').value)===BigInt(${JSON.stringify(employeeVersion)})+1n`),true);

  await navigate(manager,deptEdit);await navigate(second,deptEdit);
  const departmentVersion=await evaluate(second, `document.querySelector('[name="expected_revision"]').value`);
  await saveIn(manager,{department_name:'HR browser department current'});
  await until(manager, `location.pathname==='/departments' && document.readyState==='complete'`);
  await saveIn(second,{description:'X'.repeat(256)},true);
  await until(second, `document.readyState==='complete' && document.body.textContent.includes('Description must not exceed 255 characters.')`);
  assert.equal(await evaluate(second, `document.querySelector('[name="expected_revision"]').value`),departmentVersion);
  await saveIn(second,{description:'Stale description <script>ignored</script>'});
  await until(second, `document.readyState==='complete' && document.body.textContent.includes('This record changed since you opened the form.')`);
  assert.equal(await evaluate(second, `document.querySelectorAll('main form,main [name="expected_revision"],main script').length`),0);
  assert(await evaluate(second, `document.querySelector('main').textContent.includes('Stale description <script>ignored</script>')`));
  await navigate(second,deptEdit);
  assert.equal(await evaluate(second, `document.querySelector('[name="department_name"]').value`),'HR browser department current');
  assert.equal(await evaluate(second, `document.querySelector('[name="description"]').value`),'Corrected browser department');
  console.log('PASS Chrome independent-tab Employee/Department conflicts, stale status blocked, validation retains old revision, escaped comparison and reload without resubmission');
};
