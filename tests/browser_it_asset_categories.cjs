// Genuine native category forms against disposable MySQL; no security bypass.
const assert = require('node:assert/strict');
module.exports = async ({manager, navigate, evaluate, until, snapshot}) => {
  const base = {category_code:'browser-category-validation',category_name:'Browser category',description:'Retained <notes> & "quotes"'};
  async function submit(values, forged=false) {
    await evaluate(manager, `(() => {const f=document.querySelector('main form');
      for(const [k,v] of Object.entries(${JSON.stringify(values)})) f.elements.namedItem(k).value=v;
      ${forged ? 'HTMLFormElement.prototype.submit.call(f)' : 'f.requestSubmit()'};})()`);
  }
  async function invalid(path, field, limit, label) {
    await navigate(manager,path);
    const values={...base,[field]:'X'.repeat(limit+1)};
    const before=await snapshot();
    await submit(values,true);
    await until(manager, `document.readyState==='complete' && document.body.textContent.includes('${label} must not exceed ${limit} characters.')`);
    const retained=await evaluate(manager, `Object.fromEntries(['category_code','category_name','description'].map(k=>[k,document.querySelector('main form').elements.namedItem(k).value]))`);
    assert.deepEqual(retained,values);
    assert.equal(await snapshot(),before);
  }
  const limits=[['category_code',30,'Category code'],['category_name',100,'Category name'],['description',255,'Description']];
  for(const args of limits) await invalid('/it/assets/categories/add',...args);
  await submit(base);
  await until(manager, `location.pathname==='/it/assets/categories' && document.readyState==='complete'`);
  const edit=await evaluate(manager, `[...document.querySelectorAll('main tr')].find(r=>r.textContent.includes('BROWSER-CATEGORY-VALIDATION')).querySelector('a[href$="/edit"]').getAttribute('href')`);
  for(const args of limits) await invalid(edit,...args);
  await submit({...base,category_name:'Browser category corrected',description:''});
  await until(manager, `location.pathname==='/it/assets/categories' && document.readyState==='complete' && document.body.textContent.includes('Browser category corrected')`);
  await navigate(manager,'/it/assets/categories/add');
  const before=await snapshot();
  await submit(base);
  await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Asset category code already exists.')`);
  assert.equal(await evaluate(manager, `document.querySelector('[name="category_code"]').value`),base.category_code);
  assert.equal(await snapshot(),before);
  await navigate(manager,'/it/assets/categories');
  for(const action of ['deactivated','activated']) {
    await evaluate(manager, `[...document.querySelectorAll('main tr')].find(r=>r.textContent.includes('BROWSER-CATEGORY-VALIDATION')).querySelector('form').requestSubmit()`);
    await until(manager, `document.readyState==='complete' && document.body.textContent.includes('Asset category ${action} successfully.')`);
  }
  console.log('PASS Chrome native category Add/Edit: all length violations rejected with retained values/no writes, successful correction, duplicate retention and activation/deactivation');
};
