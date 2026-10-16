USE company_operations_erp;


-- =========================================================
-- PAYROLL APPROVAL WORKFLOW
-- =========================================================

ALTER TABLE payroll_periods

    ADD COLUMN submitted_by INT NULL
        AFTER updated_by,

    ADD COLUMN submitted_at DATETIME NULL
        AFTER submitted_by,

    ADD CONSTRAINT fk_payroll_period_submitted_by
        FOREIGN KEY (submitted_by)
        REFERENCES users(user_id);