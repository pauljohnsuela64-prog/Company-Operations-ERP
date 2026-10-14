-- =========================================================
-- IT ASSET MAINTENANCE HISTORY
-- =========================================================

CREATE TABLE IF NOT EXISTS it_asset_maintenance (

    maintenance_id INT AUTO_INCREMENT PRIMARY KEY,

    asset_id INT NOT NULL,

    maintenance_type VARCHAR(50) NOT NULL,

    description VARCHAR(255) NOT NULL,

    vendor VARCHAR(150) NULL,

    cost DECIMAL(12,2) NULL,

    start_date DATE NOT NULL,

    completed_date DATE NULL,

    status ENUM(
        'OPEN',
        'COMPLETED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'OPEN',

    notes VARCHAR(255) NULL,

    created_by INT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_it_maintenance_cost
        CHECK (
            cost IS NULL
            OR cost >= 0
        ),

    CONSTRAINT fk_it_maintenance_asset
        FOREIGN KEY (asset_id)
        REFERENCES it_assets(asset_id),

    CONSTRAINT fk_it_maintenance_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id)
);