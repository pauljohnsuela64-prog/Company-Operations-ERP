USE company_operations_erp;


-- =========================================================
-- PAYROLL ADJUSTMENTS
--
-- Earnings examples:
-- Allowance, Bonus, Incentive
--
-- Deduction examples:
-- Loan, Cash Advance, Other Deduction
-- =========================================================

CREATE TABLE IF NOT EXISTS payroll_adjustments (

    adjustment_id INT AUTO_INCREMENT PRIMARY KEY,

    payroll_entry_id INT NOT NULL,

    adjustment_type ENUM(
        'EARNING',
        'DEDUCTION'
    ) NOT NULL,

    adjustment_name VARCHAR(100)
        NOT NULL,

    amount DECIMAL(12,2)
        NOT NULL,

    notes VARCHAR(255)
        NULL,

    created_by INT
        NOT NULL,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,


    CONSTRAINT fk_payroll_adjustment_entry
        FOREIGN KEY (payroll_entry_id)
        REFERENCES payroll_entries(payroll_entry_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_payroll_adjustment_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),

    CONSTRAINT chk_payroll_adjustment_amount
        CHECK (amount > 0)
);