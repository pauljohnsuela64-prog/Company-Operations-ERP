-- =========================================================
-- IT MANAGEMENT - IT ASSETS
-- =========================================================


-- =========================================================
-- IT ASSET CATEGORIES
-- =========================================================

CREATE TABLE IF NOT EXISTS it_asset_categories (

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
-- IT ASSETS
-- =========================================================

CREATE TABLE IF NOT EXISTS it_assets (

    asset_id INT AUTO_INCREMENT PRIMARY KEY,

    asset_tag VARCHAR(50) NOT NULL UNIQUE,

    asset_name VARCHAR(150) NOT NULL,

    category_id INT NOT NULL,

    brand VARCHAR(100) NULL,

    model VARCHAR(100) NULL,

    serial_number VARCHAR(100) NULL UNIQUE,

    department_id INT NULL,

    assigned_employee_id INT NULL,

    purchase_date DATE NULL,

    purchase_cost DECIMAL(12,2) NULL,

    warranty_expiry DATE NULL,

    status ENUM(
        'AVAILABLE',
        'ASSIGNED',
        'MAINTENANCE',
        'RETIRED',
        'LOST'
    ) NOT NULL DEFAULT 'AVAILABLE',

    condition_status ENUM(
        'NEW',
        'GOOD',
        'FAIR',
        'POOR',
        'DAMAGED'
    ) NOT NULL DEFAULT 'GOOD',

    notes VARCHAR(255) NULL,

    created_by INT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    -- =====================================================
    -- FOREIGN KEYS
    -- =====================================================

    CONSTRAINT fk_it_asset_category
        FOREIGN KEY (category_id)
        REFERENCES it_asset_categories(category_id),

    CONSTRAINT fk_it_asset_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),

    CONSTRAINT fk_it_asset_employee
        FOREIGN KEY (assigned_employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_it_asset_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),


    -- =====================================================
    -- VALIDATION
    -- =====================================================

    CONSTRAINT chk_it_asset_purchase_cost
        CHECK (
            purchase_cost IS NULL
            OR purchase_cost >= 0
        )
);