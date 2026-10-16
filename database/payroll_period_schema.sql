USE company_operations_erp;


-- =========================================================
-- PAYROLL PERIODS
-- =========================================================

CREATE TABLE IF NOT EXISTS payroll_periods (

    payroll_period_id INT AUTO_INCREMENT PRIMARY KEY,

    period_number VARCHAR(50)
        NOT NULL
        UNIQUE,

    period_name VARCHAR(100)
        NOT NULL
        UNIQUE,

    start_date DATE
        NOT NULL,

    end_date DATE
        NOT NULL,

    pay_date DATE
        NOT NULL,

    status ENUM(
        'DRAFT',
        'PROCESSING',
        'APPROVED',
        'PAID',
        'CANCELLED'
    )
        NOT NULL
        DEFAULT 'DRAFT',

    notes VARCHAR(255)
        NULL,

    created_by INT
        NOT NULL,

    updated_by INT
        NULL,

    approved_by INT
        NULL,

    approved_at DATETIME
        NULL,

    paid_by INT
        NULL,

    paid_at DATETIME
        NULL,

    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,


    CONSTRAINT fk_payroll_period_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_payroll_period_updated_by
        FOREIGN KEY (updated_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_payroll_period_approved_by
        FOREIGN KEY (approved_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_payroll_period_paid_by
        FOREIGN KEY (paid_by)
        REFERENCES users(user_id),


    CONSTRAINT chk_payroll_period_dates
        CHECK (
            end_date >= start_date
        ),

    CONSTRAINT chk_payroll_period_pay_date
        CHECK (
            pay_date >= end_date
        )
);