USE company_operations_erp;


-- =========================================================
-- PAYROLL PAYMENT PERMISSION
-- =========================================================

INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'payroll.pay',
    'Mark approved payroll as paid'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'payroll.pay'
);


-- =========================================================
-- DEFAULT ACCESS
--
-- Super Admin
-- Finance Manager
-- =========================================================

INSERT IGNORE INTO role_permissions (
    role_id,
    permission_id
)
SELECT
    r.role_id,
    p.permission_id
FROM roles r
JOIN permissions p
WHERE
    r.role_name IN (
        'Super Admin',
        'Finance Manager'
    )
    AND p.permission_code = 'payroll.pay';