"""Read-only template contracts against the frozen pre-modernization tree.

Works with real route contexts on disposable suites; never opens a database.
"""
from contextlib import contextmanager
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import subprocess
import re
from zipfile import ZipFile
from flask import template_rendered
from jinja2 import DictLoader

BASELINE = '8d2a8367515d8b60152e38c280b5a5a525a72c52'
ROOT = Path(__file__).resolve().parents[1]


class Contract(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.records = []
        self.capture = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag not in ('form', 'input', 'select', 'option', 'textarea', 'button', 'a', 'script'):
            return
        # Styling, label associations and accessible names may improve. All
        # request, value, route, script and confirmation attributes must survive.
        attrs = tuple(sorted((k, ' '.join(v.split()) if k == 'onclick' else v)
                             for k, v in attrs if k not in ('class', 'id', 'style', 'title', 'tabindex') and not k.startswith('aria-')))
        self.records.append([tag, attrs, ''])
        if tag in ('textarea', 'option', 'script'):
            self.capture = len(self.records)-1

    def handle_data(self, data):
        if self.capture is not None:
            self.records[self.capture][2] += data

    def handle_endtag(self, tag):
        if tag in ('textarea', 'option', 'script'):
            self.capture = None
        if tag == 'form':
            self.records.append(['/form', (), ''])

    def normalized(self):
        return [(tag, attrs, text if tag == 'textarea' else ' '.join(text.split())) for tag, attrs, text in self.records]


@contextmanager
def watch_contracts(prefixes):
    data = subprocess.check_output(['git', 'archive', '--format=zip', BASELINE, 'templates'], cwd=ROOT)
    with ZipFile(BytesIO(data)) as archive:
        originals = {name.removeprefix('templates/'): archive.read(name).decode('utf-8') for name in archive.namelist() if name.endswith('.html')}
    # Baseline period rows had two identical View cells under one Actions
    # heading. Remove only that frozen redundant read-only cell from expected
    # markup. Every remaining route/control/script still compares exactly.
    pattern = r'(<!-- # ENTRY ACTION -->)\s*<td>\s*<a href="{{ url_for\(\s*\'view_payroll_entry\',\s*payroll_entry_id=entry.payroll_entry_id\s*\) }}" class="btn btn-sm btn-outline-primary">\s*View\s*</a>\s*</td>'
    originals['payroll/periods/view.html'], count = re.subn(pattern, r'\1', originals['payroll/periods/view.html'], count=1)
    assert count == 1, 'Frozen Payroll duplicate-link fixture changed unexpectedly'
    checked = set()

    def verify(sender, template, context, **extra):
        if not template.name or not template.name.startswith(tuple(prefixes)):
            return
        env = sender.jinja_env.overlay(loader=DictLoader(originals))
        before = env.get_template(template.name).render(context)
        after = template.render(context)
        expected, actual = Contract(before).normalized(), Contract(after).normalized()
        if actual != expected:
            from itertools import zip_longest
            first = next((pair for pair in zip_longest(expected, actual) if pair[0] != pair[1]), None)
            raise AssertionError(f'Template contract changed: {template.name}: {first}')
        checked.add(template.name)

    template_rendered.connect(verify, weak=False)
    try:
        yield checked
    finally:
        template_rendered.disconnect(verify)
