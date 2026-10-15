-- =========================================================
-- IT MANAGEMENT - HELP DESK
-- =========================================================


-- =========================================================
-- TICKET CATEGORIES
-- =========================================================

CREATE TABLE IF NOT EXISTS helpdesk_categories (

    category_id INT AUTO_INCREMENT PRIMARY KEY,

    category_code VARCHAR(30) NOT NULL UNIQUE,

    category_name VARCHAR(100) NOT NULL,

    description VARCHAR(255) NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =========================================================
-- HELP DESK TICKETS
-- =========================================================

CREATE TABLE IF NOT EXISTS helpdesk_tickets (

    ticket_id INT AUTO_INCREMENT PRIMARY KEY,

    ticket_number VARCHAR(50) NOT NULL UNIQUE,

    employee_id INT NOT NULL,

    department_id INT NULL,

    category_id INT NOT NULL,

    subject VARCHAR(150) NOT NULL,

    description TEXT NOT NULL,

    priority ENUM(
        'LOW',
        'MEDIUM',
        'HIGH',
        'URGENT'
    ) NOT NULL DEFAULT 'MEDIUM',

    status ENUM(
        'OPEN',
        'IN_PROGRESS',
        'RESOLVED',
        'CLOSED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'OPEN',

    assigned_to INT NULL,

    resolution TEXT NULL,

    created_by INT NOT NULL,

    resolved_at DATETIME NULL,

    closed_at DATETIME NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    -- =====================================================
    -- FOREIGN KEYS
    -- =====================================================

    CONSTRAINT fk_helpdesk_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_helpdesk_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),

    CONSTRAINT fk_helpdesk_category
        FOREIGN KEY (category_id)
        REFERENCES helpdesk_categories(category_id),

    CONSTRAINT fk_helpdesk_assigned_user
        FOREIGN KEY (assigned_to)
        REFERENCES users(user_id),

    CONSTRAINT fk_helpdesk_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id)
);