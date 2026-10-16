USE company_operations_erp;


-- =========================================================
-- PAYROLL PERMISSIONS
-- =========================================================

INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'payroll.view',
    'View payroll information'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'payroll.view'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'payroll.compensation.manage',
    'Manage employee compensation'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'payroll.compensation.manage'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'payroll.process',
    'Create and process payroll'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'payroll.process'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'payroll.approve',
    'Approve payroll'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'payroll.approve'
);


-- =========================================================
-- DEFAULT PAYROLL ACCESS
--
-- Payroll is sensitive.
-- Give access only to:
--
-- Super Admin
-- Finance Manager
--
-- Roles can be changed later through Role Administration.
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
    AND p.permission_code IN (
        'payroll.view',
        'payroll.compensation.manage',
        'payroll.process',
        'payroll.approve'
    );


-- =========================================================
-- EMPLOYEE COMPENSATION
-- =========================================================

CREATE TABLE IF NOT EXISTS employee_compensation (

    compensation_id INT AUTO_INCREMENT PRIMARY KEY,

    employee_id INT NOT NULL UNIQUE,

    pay_type ENUM(
        'MONTHLY',
        'DAILY',
        'HOURLY'
    ) NOT NULL,

    basic_rate DECIMAL(12,2) NOT NULL,

    currency_code CHAR(3)
        NOT NULL
        DEFAULT 'PHP',

    effective_date DATE NOT NULL,

    notes VARCHAR(255) NULL,

    created_by INT NOT NULL,

    updated_by INT NULL,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_compensation_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_compensation_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_compensation_updated_by
        FOREIGN KEY (updated_by)
        REFERENCES users(user_id),

    CONSTRAINT chk_compensation_basic_rate
        CHECK (basic_rate > 0)
);