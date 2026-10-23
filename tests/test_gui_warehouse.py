"""Warehouse presentation contracts captured from the verified parent; no database."""
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import unittest
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
# Compact original control markup keeps these contracts usable in shallow CI clones.
ORIGINAL_FORM = """<form method="POST"><input type="hidden" name="csrf_token" value="synthetic-token">
{% for name,limit in [('warehouse_code',30),('warehouse_name',100),('location',255)] %}
<input type="text" name="{{ name }}" maxlength="{{ limit }}" value="{{ request.form.get(name, (warehouse[name] or '') if editing else '') }}"{% if name != 'location' %} required{% endif %}>
{% endfor %}<button type="submit">Save</button><a href="/warehouses">Cancel</a></form>"""
ORIGINAL_LIST = """{% if has_permission('inventory.warehouses.manage') %}<a href="/add_warehouse">Add</a>{% endif %}
<form method="GET" action="/warehouses"><input name="search" maxlength="100" value="{{ filters.search }}"><select name="status"><option value=""></option>{% for value in ['active','inactive'] %}<option value="{{ value }}"{% if filters.status == value %} selected{% endif %}></option>{% endfor %}</select><select name="page_size">{% for size in [25,50,100] %}<option value="{{ size }}"{% if filters.page_size|string == size|string %} selected{% endif %}></option>{% endfor %}</select><button type="submit">Filter</button><a href="/warehouses">Clear</a></form>
{% for warehouse in warehouses %}{% if has_permission('inventory.warehouses.manage') %}
<a href="/edit_warehouse/{{ warehouse.warehouse_id }}">Edit</a><form method="POST" action="/change_warehouse_status/{{ warehouse.warehouse_id }}"><input type="hidden" name="csrf_token" value="synthetic-token"><input type="hidden" name="is_active" value="{{ '0' if warehouse.is_active else '1' }}"><button type="submit" onclick="return confirm( '{{ 'Deactivate' if warehouse.is_active else 'Activate' }} this warehouse?' )">Status</button></form>
{% endif %}{% endfor %}
{% if pagination.filters.page > 1 %}<a rel="prev" href="{{ warehouse_page_url(pagination.filters.page-1) }}">Previous</a>{% endif %}{% if pagination.filters.page < pagination.pages %}<a rel="next" href="{{ warehouse_page_url(pagination.filters.page+1) }}">Next</a>{% endif %}"""


class Controls(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.contract = []
        self.labels = []
        self.inputs = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        keys = {'input': ('type', 'name', 'maxlength', 'value', 'required'),
                'form': ('method', 'action'), 'option': ('value', 'selected'),
                'select': ('name',), 'button': ('type', 'onclick'), 'a': ('href', 'rel')}
        if tag in keys:
            self.contract.append((tag, tuple((k, ' '.join(attrs[k].split()) if k == 'onclick' else attrs[k]) for k in keys[tag] if k in attrs)))
        if tag == 'label':
            self.labels.append(attrs.get('for'))
        if tag in ('input', 'select') and attrs.get('type') != 'hidden':
            self.inputs.append(attrs.get('id'))


class WarehouseGUIContracts(unittest.TestCase):
    def render(self, name, original=False, **changes):
        path = 'templates/inventory/warehouses/' + name + '.html'
        source = (ORIGINAL_LIST if name == 'index' else ORIGINAL_FORM) if original else (ROOT/path).read_text()
        env = Environment(loader=ChoiceLoader([DictLoader({'base.html': '{% block content %}{% endblock %}'}), FileSystemLoader(ROOT/'templates')]), autoescape=select_autoescape(default=True))
        filters = dict(search='', status='', page_size=25, page=2)
        warehouse = dict(warehouse_id=7, warehouse_code='MAIN', warehouse_name='<Long name>', location=None, is_active=True)
        context = dict(editing=name == 'edit', filters=filters, warehouses=[warehouse], warehouse=warehouse, load_error=False,
                       pagination=dict(first=26, last=50, total=70, pages=3, filters=filters),
                       request=SimpleNamespace(form={}), csrf_token=lambda: 'synthetic-token',
                       has_permission=lambda permission: permission == 'inventory.warehouses.manage',
                       url_for=lambda endpoint, **kw: '/' + endpoint + ('/'+str(kw['warehouse_id']) if kw else ''),
                       warehouse_page_url=lambda page: '?search=retained&status=inactive&page_size=25&page='+str(page))
        context.update(changes)
        return env.from_string(source).render(**context)

    def test_parent_contracts_and_label_associations(self):
        for name in ('index', 'add', 'edit'):
            for manager in (False, True):
                for active in (False, True):
                    for submitted in ({}, dict(warehouse_code='submitted', warehouse_name='<submitted>', location='')):
                        warehouse = dict(warehouse_id=7, warehouse_code='MAIN', warehouse_name='Original', location=None, is_active=active)
                        data = dict(has_permission=lambda p: manager, warehouse=warehouse, warehouses=[warehouse], request=SimpleNamespace(form=submitted))
                        with self.subTest(name=name, manager=manager, active=active, submitted=submitted):
                            before = Controls(self.render(name, True, **data))
                            after = Controls(self.render(name, **data))
                            self.assertEqual(before.contract, after.contract)
                            self.assertTrue(all(i and i in after.labels for i in after.inputs))

    def test_distinct_empty_filtered_and_unavailable_states(self):
        empty = self.render('index', warehouses=[])
        self.assertIn('No warehouses found.', empty)
        filtered = self.render('index', warehouses=[], filters=dict(search='missing', status='', page_size=25))
        self.assertIn('No warehouses match these filters.', filtered)
        unavailable = self.render('index', warehouses=[], load_error=True)
        self.assertIn('Unable to display records', unavailable)
        self.assertIn('Results unavailable', unavailable)
        self.assertNotIn('matching warehouses', unavailable)
        self.assertNotIn('Warehouse pages', unavailable)

    def test_badges_escaping_and_scroll_region(self):
        source = self.render('index')
        self.assertIn('status-active', source)
        self.assertIn('&lt;Long name&gt;', source)
        self.assertIn('tabindex="0"', source)
        self.assertIn('scope="col"', source)
        self.assertIn('rel="next"', source)
        self.assertIn('rel="prev"', source)


if __name__ == '__main__':
    unittest.main()
