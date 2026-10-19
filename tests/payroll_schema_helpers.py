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


def upgrade_certification_workflow(connect):
    """Explicit disposable-fixture upgrade; 007 verifies the extended 006 contract."""
    upgrade_policy_foundation(connect)
    with connect() as connection:
        cursor=connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_cutoff_certifications' AND column_name='correction_reason'")
        extended=cursor.fetchone()[0]>0;cursor.close()
    for name in (() if extended else ('006_payroll_certification.py',))+('007_payroll_correction_references.py',):
        spec=spec_from_file_location('fixture_'+name[:3],Path(__file__).resolve().parents[1]/'database/migrations'/name)
        migration=module_from_spec(spec);spec.loader.exec_module(migration)
        with connect() as connection:migration.upgrade(connection)
