-- =========================================================
-- FINANCE MODULE
-- =========================================================


-- =========================================================
-- EXPENSE CATEGORIES
--
-- Examples:
-- Utilities
-- Transportation
-- Office Supplies
-- Repairs
-- Software
-- Procurement
-- =========================================================

CREATE TABLE IF NOT EXISTS expense_categories (

    category_id INT
        AUTO_INCREMENT
        PRIMARY KEY,

    category_code VARCHAR(30)
        NOT NULL
        UNIQUE,

    category_name VARCHAR(100)
        NOT NULL,

    description VARCHAR(255)
        NULL,

    is_active BOOLEAN
        NOT NULL
        DEFAULT TRUE,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP

);


-- =========================================================
-- EXPENSES
-- =========================================================

CREATE TABLE IF NOT EXISTS expenses (

    expense_id INT
        AUTO_INCREMENT
        PRIMARY KEY,

    expense_number VARCHAR(50)
        NOT NULL
        UNIQUE,

    expense_date DATE
        NOT NULL,

    category_id INT
        NOT NULL,

    department_id INT
        NULL,

    supplier_id INT
        NULL,

    purchase_order_id INT
        NULL,

    description VARCHAR(255)
        NOT NULL,

    amount DECIMAL(12, 2)
        NOT NULL,

    reference_number VARCHAR(100)
        NULL,

    payment_method ENUM(
        'CASH',
        'BANK_TRANSFER',
        'CHECK',
        'CARD',
        'OTHER'
    )
        NULL,

    status ENUM(
        'DRAFT',
        'APPROVED',
        'PAID',
        'CANCELLED'
    )
        NOT NULL
        DEFAULT 'DRAFT',

    created_by INT
        NOT NULL,

    approved_by INT
        NULL,

    approved_at DATETIME
        NULL,

    paid_at DATETIME
        NULL,

    notes VARCHAR(255)
        NULL,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    CONSTRAINT chk_expense_amount
        CHECK (amount > 0),


    CONSTRAINT fk_expense_category
        FOREIGN KEY (category_id)
        REFERENCES expense_categories(category_id),


    CONSTRAINT fk_expense_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),


    CONSTRAINT fk_expense_supplier
        FOREIGN KEY (supplier_id)
        REFERENCES suppliers(supplier_id),


    CONSTRAINT fk_expense_purchase_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(purchase_order_id),


    CONSTRAINT fk_expense_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),


    CONSTRAINT fk_expense_approved_by
        FOREIGN KEY (approved_by)
        REFERENCES users(user_id)

);