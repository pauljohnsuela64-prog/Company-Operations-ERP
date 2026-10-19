"""Shared local/Actions checks; never load application configuration or company data."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def tracked_files():
    output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    return [ROOT / name.decode('utf-8') for name in output.split(b'\0') if name]


def python_syntax():
    from jinja2 import Environment
    sources = [p for p in tracked_files() if p.suffix == '.py']
    # Include this new helper before it has been staged in a local checkout.
    sources = sorted(set(sources + [Path(__file__).resolve()]))
    for path in sources:
        compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
    templates = sorted((ROOT / 'templates').rglob('*.html'))
    for path in templates:
        Environment().parse(path.read_text(encoding='utf-8'), name=str(path), filename=str(path))
    print(f'PASS Python compilation: {len(sources)} files; Jinja syntax: {len(templates)} templates', flush=True)


def javascript_syntax():
    sources = [p for p in tracked_files() if p.suffix in ('.js', '.cjs')]
    for path in sources:
        print('JavaScript syntax:', path.relative_to(ROOT), flush=True)
        subprocess.run(['node', '--check', str(path)], check=True, cwd=ROOT)
    print(f'PASS JavaScript syntax: {len(sources)} files', flush=True)


def mysql_binary(explicit=None):
    if explicit:
        candidates = [Path(explicit)]
    else:
        found = shutil.which('mysqld')
        candidates = [Path(found)] if found else []
        # Discover the installed binary; no workstation-specific absolute path.
        program_files = os.environ.get('ProgramFiles')
        if program_files:
            candidates += sorted((Path(program_files) / 'MySQL').glob('*/bin/mysqld.exe'))
    for path in candidates:
        if not path.is_file():
            continue
        result = subprocess.run([str(path), '--no-defaults', '--version'],
                                capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        match = re.search(r'\bVer (\d+)\.(\d+)\.(\d+)', version)
        if (match and tuple(map(int, match.groups())) >= (8, 0, 16)
                and 'mariadb' not in version.lower()):
            print('Disposable MySQL binary:', version, flush=True)
            return path.resolve()
    raise RuntimeError('Compatible MySQL 8.0.16+ mysqld not found; integration checks were NOT run.')


def mysql_suites(explicit=None):
    binary = mysql_binary(explicit)
    suites = sorted((ROOT / 'tests').glob('mysql_*_smoke.py'))
    # mysql_audit_smoke is also a suite, not merely the shared launcher.
    if not suites:
        raise RuntimeError('No disposable MySQL suites discovered.')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    for path in suites:
        print(f'::group::{path.name}', flush=True)
        try:
            subprocess.run([sys.executable, '-u', '-B', str(path), '--mysqld', str(binary)],
                           cwd=ROOT, env=env, check=True, timeout=300)
        finally:
            print('::endgroup::', flush=True)
    print(f'PASS {len(suites)}/{len(suites)} disposable MySQL suites', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=('python', 'javascript', 'mysql'))
    parser.add_argument('--mysqld', help='Explicit local server binary; never a database target')
    args = parser.parse_args()
    try:
        if args.check == 'python':
            python_syntax()
        elif args.check == 'javascript':
            javascript_syntax()
        else:
            mysql_suites(args.mysqld)
    except (OSError, RuntimeError, SyntaxError, subprocess.SubprocessError) as error:
        print(f'FAILED {args.check}: {error}', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
