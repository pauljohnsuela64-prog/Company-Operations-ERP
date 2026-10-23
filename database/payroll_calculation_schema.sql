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

    ADD COLUMN calculated_by INT
        NULL,

    ADD COLUMN calculated_at DATETIME
        NULL,

    ADD CONSTRAINT fk_payroll_entry_calculated_by
        FOREIGN KEY (calculated_by)
        REFERENCES users(user_id);

-- Payroll attendance freshness: additive structures, no legacy evidence backfill.
ALTER TABLE payroll_entries
    ADD COLUMN attendance_evidence_version SMALLINT UNSIGNED NULL,
    ADD COLUMN attendance_scope_start DATE NULL,
    ADD COLUMN attendance_scope_end DATE NULL;
CREATE TABLE IF NOT EXISTS payroll_attendance_snapshots (
    payroll_entry_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    employee_id INT NOT NULL,
    generation BIGINT NOT NULL,
    PRIMARY KEY (payroll_entry_id, attendance_date),
    CONSTRAINT ck_payroll_attendance_snapshot_nonnegative CHECK (generation >= 0),
    CONSTRAINT fk_payroll_attendance_snapshot_entry FOREIGN KEY (payroll_entry_id)
        REFERENCES payroll_entries(payroll_entry_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB;
