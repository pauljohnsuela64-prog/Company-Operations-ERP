USE company_operations_erp;


-- =========================================================
-- LEAVE PERMISSIONS
-- =========================================================

INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'leave.view',
    'View leave management records'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'leave.view'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'leave.manage',
    'Create and manage leave records'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'leave.manage'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'leave.approve',
    'Approve or reject leave requests'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'leave.approve'
);


-- =========================================================
-- DEFAULT ROLE PERMISSIONS
--
-- Super Admin + HR Manager
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
        'HR Manager'
    )
    AND p.permission_code IN (
        'leave.view',
        'leave.manage',
        'leave.approve'
    );


-- =========================================================
-- LEAVE TYPES
-- =========================================================

CREATE TABLE IF NOT EXISTS leave_types (

    leave_type_id INT AUTO_INCREMENT PRIMARY KEY,

    leave_code VARCHAR(30) NOT NULL UNIQUE,

    leave_name VARCHAR(100) NOT NULL UNIQUE,

    description VARCHAR(255) NULL,

    annual_entitlement DECIMAL(5,2) NULL,

    is_paid TINYINT(1) NOT NULL DEFAULT 1,

    is_active TINYINT(1) NOT NULL DEFAULT 1,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =========================================================
-- STARTER LEAVE TYPES
-- =========================================================

INSERT IGNORE INTO leave_types (
    leave_code,
    leave_name,
    description,
    annual_entitlement,
    is_paid
)
VALUES

(
    'VL',
    'Vacation Leave',
    'Planned personal or vacation leave',
    5.00,
    1
),

(
    'SL',
    'Sick Leave',
    'Leave due to illness or medical reasons',
    5.00,
    1
),

(
    'EL',
    'Emergency Leave',
    'Leave for urgent personal emergencies',
    NULL,
    1
),

(
    'UL',
    'Unpaid Leave',
    'Approved leave without pay',
    NULL,
    0
);


-- =========================================================
-- LEAVE REQUESTS
-- =========================================================

CREATE TABLE IF NOT EXISTS leave_requests (

    leave_request_id INT AUTO_INCREMENT PRIMARY KEY,

    request_number VARCHAR(50) NOT NULL UNIQUE,

    employee_id INT NOT NULL,

    leave_type_id INT NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    total_days DECIMAL(5,2) NOT NULL,

    reason VARCHAR(500) NOT NULL,

    status ENUM(
        'PENDING',
        'APPROVED',
        'REJECTED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'PENDING',

    requested_by INT NOT NULL,

    reviewed_by INT NULL,

    reviewed_at DATETIME NULL,

    rejection_reason VARCHAR(500) NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_leave_request_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_leave_request_type
        FOREIGN KEY (leave_type_id)
        REFERENCES leave_types(leave_type_id),

    CONSTRAINT fk_leave_requested_by
        FOREIGN KEY (requested_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_leave_reviewed_by
        FOREIGN KEY (reviewed_by)
        REFERENCES users(user_id)
);