USE company_operations_erp;


-- =========================================================
-- ATTENDANCE PERMISSIONS
-- =========================================================

INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'attendance.view',
    'View employee attendance'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'attendance.view'
);


INSERT INTO permissions (
    permission_code,
    description
)
SELECT
    'attendance.manage',
    'Create and manage employee attendance'
WHERE NOT EXISTS (
    SELECT 1
    FROM permissions
    WHERE permission_code = 'attendance.manage'
);


-- =========================================================
-- GRANT ATTENDANCE PERMISSIONS
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
        'attendance.view',
        'attendance.manage'
    );


-- =========================================================
-- ATTENDANCE RECORDS
-- =========================================================

CREATE TABLE IF NOT EXISTS attendance_records (

    attendance_id INT AUTO_INCREMENT PRIMARY KEY,

    employee_id INT NOT NULL,

    attendance_date DATE NOT NULL,

    time_in TIME NULL,

    time_out TIME NULL,

    status ENUM(
        'PRESENT',
        'LATE',
        'ABSENT',
        'ON_LEAVE',
        'HALF_DAY'
    ) NOT NULL DEFAULT 'PRESENT',

    notes VARCHAR(255) NULL,

    created_by INT NOT NULL,

    updated_by INT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT uq_attendance_employee_date
        UNIQUE (
            employee_id,
            attendance_date
        ),

    CONSTRAINT fk_attendance_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_attendance_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_attendance_updated_by
        FOREIGN KEY (updated_by)
        REFERENCES users(user_id)
);