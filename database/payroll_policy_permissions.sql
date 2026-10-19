-- Explicit registration only. Run through an approved upgrade process, never on app startup.
-- No role grants, approved policies or activations are created.
INSERT INTO permissions (permission_code, description)
SELECT 'payroll.policy.manage', 'Create and edit draft payroll policies'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE permission_code='payroll.policy.manage');

INSERT INTO permissions (permission_code, description)
SELECT 'payroll.policy.approve', 'Approve payroll policy configurations'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE permission_code='payroll.policy.approve');

INSERT INTO permissions (permission_code, description)
SELECT 'payroll.policy.activate', 'Schedule approved payroll policy activations'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE permission_code='payroll.policy.activate');
