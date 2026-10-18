USE company_operations_erp;


-- =========================================================
-- PAYROLL CALCULATION DETAILS
-- =========================================================

ALTER TABLE payroll_entries

    ADD COLUMN scheduled_work_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN present_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN late_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN absent_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN paid_leave_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN unpaid_leave_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN half_day_count INT
        NOT NULL DEFAULT 0,

    ADD COLUMN unrecorded_days INT
        NOT NULL DEFAULT 0,

    ADD COLUMN daily_rate DECIMAL(12,2)
        NOT NULL DEFAULT 0.00,

    ADD COLUMN attendance_deduction DECIMAL(12,2)
        NOT NULL DEFAULT 0.00,

    ADD COLUMN calculation_input_version SMALLINT UNSIGNED NULL,

    ADD COLUMN calculation_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,

    ADD COLUMN calculated_by INT
        NULL,

    ADD COLUMN calculated_at DATETIME
        NULL,

    ADD CONSTRAINT fk_payroll_entry_calculated_by
        FOREIGN KEY (calculated_by)
        REFERENCES users(user_id);