"""Explicit upgrades for disposable Payroll tests; never connects on import."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path


def upgrade_policy_foundation(connect):
    for name in ('004_payroll_freshness.py', '005_payroll_policy.py'):
        spec = spec_from_file_location('fixture_' + name[:3],
                                      Path(__file__).resolve().parents[1]/'database/migrations'/name)
        migration = module_from_spec(spec)
        spec.loader.exec_module(migration)
        with connect() as connection:
            migration.upgrade(connection)
