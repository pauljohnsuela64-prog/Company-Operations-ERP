USE company_operations_erp;


-- =========================================================
-- PAYROLL ENTRIES
-- =========================================================

CREATE TABLE IF NOT EXISTS payroll_entries (

    payroll_entry_id INT AUTO_INCREMENT PRIMARY KEY,

    payroll_period_id INT NOT NULL,

    employee_id INT NOT NULL,

    compensation_id INT NOT NULL,


    -- =====================================================
    -- COMPENSATION SNAPSHOT
    --
    -- We save the values used when this payroll entry
    -- was generated so later compensation edits do not
    -- change this payroll run.
    -- =====================================================

    pay_type ENUM(
        'MONTHLY',
        'DAILY',
        'HOURLY'
    ) NOT NULL,

    basic_rate DECIMAL(12,2) NOT NULL,

    currency_code CHAR(3)
        NOT NULL
        DEFAULT 'PHP',


    -- =====================================================
    -- PAYROLL CALCULATION FIELDS
    --
    -- These remain zero for now.
    -- The next payroll feature will calculate them using
    -- Attendance, Leave, earnings, and deductions.
    -- =====================================================

    regular_pay DECIMAL(12,2)
        NOT NULL
        DEFAULT 0.00,

    additional_earnings DECIMAL(12,2)
        NOT NULL
        DEFAULT 0.00,

    gross_pay DECIMAL(12,2)
        NOT NULL
        DEFAULT 0.00,

    total_deductions DECIMAL(12,2)
        NOT NULL
        DEFAULT 0.00,

    net_pay DECIMAL(12,2)
        NOT NULL
        DEFAULT 0.00,


    status ENUM(
        'DRAFT',
        'CALCULATED',
        'APPROVED',
        'PAID'
    )
        NOT NULL
        DEFAULT 'DRAFT',


    generated_by INT NOT NULL,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    -- =====================================================
    -- FOREIGN KEYS
    -- =====================================================

    CONSTRAINT fk_payroll_entry_period
        FOREIGN KEY (payroll_period_id)
        REFERENCES payroll_periods(payroll_period_id),

    CONSTRAINT fk_payroll_entry_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_payroll_entry_compensation
        FOREIGN KEY (compensation_id)
        REFERENCES employee_compensation(compensation_id),

    CONSTRAINT fk_payroll_entry_generated_by
        FOREIGN KEY (generated_by)
        REFERENCES users(user_id),


    -- =====================================================
    -- ONE EMPLOYEE = ONE ENTRY PER PAYROLL PERIOD
    -- =====================================================

    CONSTRAINT uq_payroll_entry_employee_period
        UNIQUE (
            payroll_period_id,
            employee_id
        ),


    -- =====================================================
    -- MONEY VALIDATION
    -- =====================================================

    CONSTRAINT chk_payroll_entry_basic_rate
        CHECK (basic_rate > 0),

    CONSTRAINT chk_payroll_entry_regular_pay
        CHECK (regular_pay >= 0),

    CONSTRAINT chk_payroll_entry_additional_earnings
        CHECK (additional_earnings >= 0),

    CONSTRAINT chk_payroll_entry_gross_pay
        CHECK (gross_pay >= 0),

    CONSTRAINT chk_payroll_entry_deductions
        CHECK (total_deductions >= 0),

    CONSTRAINT chk_payroll_entry_net_pay
        CHECK (net_pay >= 0)
);