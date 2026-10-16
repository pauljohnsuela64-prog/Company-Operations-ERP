USE company_operations_erp;


-- =========================================================
-- ERP AUDIT LOGS
-- =========================================================

CREATE TABLE IF NOT EXISTS audit_logs (

    audit_log_id BIGINT
        AUTO_INCREMENT
        PRIMARY KEY,

    user_id INT
        NULL,

    username VARCHAR(100)
        NOT NULL,

    module VARCHAR(50)
        NOT NULL,

    action VARCHAR(50)
        NOT NULL,

    entity_type VARCHAR(50)
        NULL,

    entity_id VARCHAR(100)
        NULL,

    description VARCHAR(500)
        NULL,

    created_at TIMESTAMP
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,


    CONSTRAINT fk_audit_logs_user

        FOREIGN KEY (user_id)

        REFERENCES users(user_id)

        ON DELETE SET NULL,


    INDEX idx_audit_logs_created_at (
        created_at
    ),

    INDEX idx_audit_logs_module (
        module
    ),

    INDEX idx_audit_logs_action (
        action
    ),

    INDEX idx_audit_logs_user (
        user_id
    )
);