"""Run an existing disposable suite with baseline template-contract checks."""
import argparse
from pathlib import Path
import runpy
import sys
from gui_contracts import watch_contracts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite')
    parser.add_argument('prefixes', nargs='+')
    args = parser.parse_args()
    suite = Path(__file__).resolve().parent / args.suite
    if suite.parent != Path(__file__).resolve().parent or not suite.name.startswith('mysql_'):
        raise ValueError('Only existing disposable MySQL suite entrypoints are allowed')
    sys.argv = [str(suite)]
    with watch_contracts(args.prefixes) as checked:
        runpy.run_path(str(suite), run_name='__main__')
    assert checked, 'No in-scope templates rendered; verification is incomplete'
    print('PASS unchanged baseline form/link/script contracts:', ', '.join(sorted(checked)))


if __name__ == '__main__':
    main()
