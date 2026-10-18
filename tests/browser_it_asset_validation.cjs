// Native form redisplay/correction against the disposable Chrome/MySQL fixture.
const assert = require('node:assert/strict');

module.exports = async ({manager, navigate, evaluate, until, request, snapshot}) => {
  async function submit(values, invalid=false) {
    await evaluate(manager, `(() => {const f=document.querySelector('main form');
      for(const [name,value] of Object.entries(${JSON.stringify(values)}))f.elements.namedItem(name).value=value;
      ${invalid ? 'HTMLFormElement.prototype.submit.call(f)' : 'f.requestSubmit()'};})()`);
  }
  const form={asset_tag:'BROWSER-VALIDATION',asset_name:'Browser validation asset',category_id:'1',
    department_id:'1',assigned_employee_id:'1',brand:'Brand',model:'Model',serial_number:'BROWSER-VALIDATION',
    purchase_date:'2026-01-01',purchase_cost:'0.001',warranty_expiry:'2027-01-01',condition_status:'GOOD',notes:'Retained asset notes'};
  await navigate(manager,'/it/assets/add');
  await submit(form,true); // Invalid native POST still uses genuine CSRF/server validation.
  await until(manager, `document.body.textContent.includes('at most two decimal places') && document.readyState === 'complete'`);
  const values=await evaluate(manager, `Object.fromEntries([...document.querySelector('main form').elements].filter(e=>e.name).map(e=>[e.name,e.value]))`);
  for(const [name,value] of Object.entries(form))assert.equal(values[name],value,name);
  await submit({purchase_cost:'0.20'});
  await until(manager, `location.pathname === '/it/assets' && document.readyState === 'complete'`);
  const path=await evaluate(manager, `[...document.querySelectorAll('tr')].find(r=>r.textContent.includes('BROWSER-VALIDATION')).querySelector('a[href*="/it/assets/"]').getAttribute('href')`);
  await navigate(manager,path+'/edit');
  await submit({asset_name:'Edited browser asset',condition_status:'FAIR',purchase_cost:'0.001'},true);
  await until(manager, `document.body.textContent.includes('at most two decimal places') && document.readyState === 'complete'`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="asset_name"]').value`),'Edited browser asset');
  assert.equal(await evaluate(manager, `document.querySelector('[name="condition_status"]').value`),'FAIR');
  await submit({purchase_cost:'0.00'});
  await until(manager, `location.pathname === ${JSON.stringify(path)} && document.readyState === 'complete'`);
  await navigate(manager,path+'/edit');
  assert.equal(await evaluate(manager, `document.querySelector('[name="purchase_cost"]').value`),'0.00');
  await navigate(manager,'/it/assets/add');
  await submit({...form,purchase_cost:'0.20'});
  await until(manager, `document.body.textContent.includes('Asset tag or serial number already exists.') && document.readyState === 'complete'`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="assigned_employee_id"]').value`),'1');
  await navigate(manager,path+'/maintenance/add');
  const maintenance={maintenance_type:'Repair',description:'Browser repair',vendor:'Vendor',cost:'0.001',start_date:'2026-10-01',notes:'Retained maintenance notes'};
  await submit(maintenance,true);
  await until(manager, `document.body.textContent.includes('at most two decimal places') && document.readyState === 'complete'`);
  for(const [name,value] of Object.entries(maintenance))assert.equal(await evaluate(manager, `document.querySelector('[name="${name}"]').value`),value,name);
  await submit({cost:'0.00'});
  await until(manager, `location.pathname === ${JSON.stringify(path)} && document.readyState === 'complete'`);
  const completion=await evaluate(manager, `document.querySelector('main form[action$="/complete"]').getAttribute('action')`);
  const before=await snapshot();
  const rejected=await request(manager,completion,{completed_date:'2026-09-30'});
  assert(rejected.text.includes('Completion date cannot be before maintenance start date.'));
  assert.equal(await snapshot(),before);
  assert.equal((await request(manager,completion,{completed_date:'2026-10-01'})).path,path);
  await navigate(manager,path);
  assert(await evaluate(manager, `Boolean(document.querySelector('main form[action="${path}/unassign"]'))`));
  assert.equal((await request(manager,path+'/unassign')).path,path);
  console.log('PASS Chrome native asset Add/Edit/maintenance validation, retained fields, duplicate identifiers, zero cost and chronological completion without custody loss');
};
