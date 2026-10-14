-- =========================================================
-- FINANCE - DEPARTMENT BUDGETS
-- =========================================================

CREATE TABLE IF NOT EXISTS department_budgets (

    budget_id INT AUTO_INCREMENT PRIMARY KEY,

    -- # DEPARTMENT
    department_id INT NOT NULL,

    -- # BUDGET YEAR
    budget_year INT NOT NULL,

    -- # APPROVED BUDGET AMOUNT
    budget_amount DECIMAL(14, 2) NOT NULL,

    -- # OPTIONAL NOTES
    notes VARCHAR(255) NULL,

    -- # USER WHO CREATED THE BUDGET
    created_by INT NOT NULL,

    -- # TIMESTAMPS
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    -- =====================================================
    -- # ONE BUDGET PER DEPARTMENT PER YEAR
    -- =====================================================

    CONSTRAINT uq_department_budget_year
        UNIQUE (
            department_id,
            budget_year
        ),


    -- =====================================================
    -- # VALIDATION
    -- =====================================================

    CONSTRAINT chk_budget_amount_positive
        CHECK (budget_amount > 0),


    -- =====================================================
    -- # FOREIGN KEYS
    -- =====================================================

    CONSTRAINT fk_budget_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),

    CONSTRAINT fk_budget_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id)

);