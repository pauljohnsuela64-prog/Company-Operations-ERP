USE company_operations_erp;


-- =========================================================
-- INVENTORY CATEGORIES
-- =========================================================

CREATE TABLE IF NOT EXISTS inventory_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,

    category_code VARCHAR(30) NOT NULL UNIQUE,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =========================================================
-- WAREHOUSES
-- =========================================================

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id INT AUTO_INCREMENT PRIMARY KEY,

    warehouse_code VARCHAR(30) NOT NULL UNIQUE,
    warehouse_name VARCHAR(100) NOT NULL UNIQUE,
    location VARCHAR(255),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =========================================================
-- INVENTORY ITEMS
-- =========================================================

CREATE TABLE IF NOT EXISTS inventory_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,

    item_code VARCHAR(50) NOT NULL UNIQUE,
    item_name VARCHAR(150) NOT NULL,

    category_id INT,

    description VARCHAR(255),

    unit_of_measure VARCHAR(30) NOT NULL DEFAULT 'pcs',

    reorder_level DECIMAL(12,2)
        NOT NULL DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_inventory_items_category
        FOREIGN KEY (category_id)
        REFERENCES inventory_categories(category_id)
        ON DELETE SET NULL
);


-- =========================================================
-- INVENTORY STOCK
-- =========================================================

CREATE TABLE IF NOT EXISTS inventory_stock (
    item_id INT NOT NULL,
    warehouse_id INT NOT NULL,

    quantity DECIMAL(12,2)
        NOT NULL DEFAULT 0,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (
        item_id,
        warehouse_id
    ),

    CONSTRAINT fk_inventory_stock_item
        FOREIGN KEY (item_id)
        REFERENCES inventory_items(item_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_inventory_stock_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(warehouse_id)
        ON DELETE RESTRICT
);


-- =========================================================
-- STOCK MOVEMENTS
-- =========================================================

CREATE TABLE IF NOT EXISTS stock_movements (
    movement_id INT AUTO_INCREMENT PRIMARY KEY,

    item_id INT NOT NULL,
    warehouse_id INT NOT NULL,

    movement_type VARCHAR(30) NOT NULL,

    quantity DECIMAL(12,2) NOT NULL,

    reference_type VARCHAR(50),
    reference_id INT,

    notes VARCHAR(255),

    created_by INT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_stock_movements_item
        FOREIGN KEY (item_id)
        REFERENCES inventory_items(item_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_stock_movements_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(warehouse_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_stock_movements_user
        FOREIGN KEY (created_by)
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_stock_movement_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_stock_movement_type
        CHECK (
            movement_type IN (
                'IN',
                'OUT',
                'ADJUSTMENT_IN',
                'ADJUSTMENT_OUT'
            )
        )
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_inventory_items_category
    ON inventory_items(category_id);

CREATE INDEX idx_stock_movements_item
    ON stock_movements(item_id);

CREATE INDEX idx_stock_movements_warehouse
    ON stock_movements(warehouse_id);

CREATE INDEX idx_stock_movements_created_at
    ON stock_movements(created_at);