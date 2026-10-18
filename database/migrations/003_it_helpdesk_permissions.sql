-- Reviewed scope: existing seed mapping only; no role creation or grant copying.
-- Run against an explicitly selected database after reviewing IT_AUTHORIZATION.md.
START TRANSACTION;
INSERT IGNORE INTO permissions (permission_code, description) VALUES
('it_assets.view', 'View IT assets'),
('it_assets.manage', 'Manage IT assets'),
('helpdesk.view', 'View help desk tickets'),
('helpdesk.manage', 'Manage help desk tickets');
INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM roles r CROSS JOIN permissions p
WHERE r.role_name IN ('Super Admin', 'IT Manager')
AND p.permission_code IN ('it_assets.view', 'it_assets.manage', 'helpdesk.view', 'helpdesk.manage');
COMMIT;
