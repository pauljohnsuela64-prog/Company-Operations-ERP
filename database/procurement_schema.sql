USE company_operations_erp;


-- =========================================================
-- SUPPLIERS
-- =========================================================

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,

    supplier_code VARCHAR(30) NOT NULL UNIQUE,
    supplier_name VARCHAR(150) NOT NULL,

    contact_person VARCHAR(100),
    email VARCHAR(150),
    phone VARCHAR(30),
    address VARCHAR(255),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- =========================================================
-- PURCHASE REQUESTS
-- =========================================================

CREATE TABLE IF NOT EXISTS purchase_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,

    request_number VARCHAR(50) NOT NULL UNIQUE,

    requested_by INT NOT NULL,
    department_id INT,

    purpose VARCHAR(255),

    status VARCHAR(30)
        NOT NULL DEFAULT 'DRAFT',

    submitted_at DATETIME,

    approved_by INT,
    approved_at DATETIME,

    rejection_reason VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_purchase_requests_requested_by
        FOREIGN KEY (requested_by)
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_purchase_requests_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_purchase_requests_approved_by
        FOREIGN KEY (approved_by)
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_purchase_request_status
        CHECK (
            status IN (
                'DRAFT',
                'SUBMITTED',
                'APPROVED',
                'REJECTED',
                'CANCELLED',
                'COMPLETED'
            )
        )
);


-- =========================================================
-- PURCHASE REQUEST ITEMS
-- =========================================================

CREATE TABLE IF NOT EXISTS purchase_request_items (
    request_item_id INT AUTO_INCREMENT PRIMARY KEY,

    request_id INT NOT NULL,
    item_id INT NOT NULL,

    quantity DECIMAL(12,2) NOT NULL,

    estimated_unit_cost DECIMAL(12,2),

    notes VARCHAR(255),

    CONSTRAINT fk_purchase_request_items_request
        FOREIGN KEY (request_id)
        REFERENCES purchase_requests(request_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_purchase_request_items_item
        FOREIGN KEY (item_id)
        REFERENCES inventory_items(item_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_purchase_request_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_purchase_request_estimated_cost
        CHECK (
            estimated_unit_cost IS NULL
            OR estimated_unit_cost >= 0
        )
);


-- =========================================================
-- PURCHASE ORDERS
-- =========================================================

CREATE TABLE IF NOT EXISTS purchase_orders (
    purchase_order_id INT AUTO_INCREMENT PRIMARY KEY,

    po_number VARCHAR(50) NOT NULL UNIQUE,

    request_id INT,
    supplier_id INT NOT NULL,

    created_by INT NOT NULL,

    status VARCHAR(30)
        NOT NULL DEFAULT 'DRAFT',

    order_date DATE,
    expected_delivery_date DATE,

    notes VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_purchase_orders_request
        FOREIGN KEY (request_id)
        REFERENCES purchase_requests(request_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_purchase_orders_supplier
        FOREIGN KEY (supplier_id)
        REFERENCES suppliers(supplier_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_purchase_orders_created_by
        FOREIGN KEY (created_by)
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_purchase_order_status
        CHECK (
            status IN (
                'DRAFT',
                'SENT',
                'PARTIALLY_RECEIVED',
                'RECEIVED',
                'CANCELLED'
            )
        )
);


-- =========================================================
-- PURCHASE ORDER ITEMS
-- =========================================================

CREATE TABLE IF NOT EXISTS purchase_order_items (
    purchase_order_item_id INT AUTO_INCREMENT PRIMARY KEY,

    purchase_order_id INT NOT NULL,

    request_item_id INT,
    item_id INT NOT NULL,

    quantity DECIMAL(12,2) NOT NULL,
    unit_cost DECIMAL(12,2) NOT NULL,

    notes VARCHAR(255),

    CONSTRAINT fk_purchase_order_items_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(purchase_order_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_purchase_order_items_request_item
        FOREIGN KEY (request_item_id)
        REFERENCES purchase_request_items(request_item_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_purchase_order_items_item
        FOREIGN KEY (item_id)
        REFERENCES inventory_items(item_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_purchase_order_item_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_purchase_order_item_cost
        CHECK (unit_cost >= 0)
);


-- =========================================================
-- GOODS RECEIPTS
-- =========================================================

CREATE TABLE IF NOT EXISTS goods_receipts (
    receipt_id INT AUTO_INCREMENT PRIMARY KEY,

    receipt_number VARCHAR(50) NOT NULL UNIQUE,

    -- NULL permits historical rows; every new application submission supplies a UUID.
    submission_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
    CONSTRAINT uq_goods_receipts_submission UNIQUE (submission_id),

    purchase_order_id INT NOT NULL,
    warehouse_id INT NOT NULL,

    received_by INT NOT NULL,

    received_at DATETIME
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    notes VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_goods_receipts_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(purchase_order_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_goods_receipts_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(warehouse_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_goods_receipts_received_by
        FOREIGN KEY (received_by)
        REFERENCES users(user_id)
        ON DELETE RESTRICT
);


-- =========================================================
-- GOODS RECEIPT ITEMS
-- =========================================================

CREATE TABLE IF NOT EXISTS goods_receipt_items (
    receipt_item_id INT AUTO_INCREMENT PRIMARY KEY,

    receipt_id INT NOT NULL,
    purchase_order_item_id INT NOT NULL,

    quantity_received DECIMAL(12,2) NOT NULL,

    CONSTRAINT fk_goods_receipt_items_receipt
        FOREIGN KEY (receipt_id)
        REFERENCES goods_receipts(receipt_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_goods_receipt_items_po_item
        FOREIGN KEY (purchase_order_item_id)
        REFERENCES purchase_order_items(purchase_order_item_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_goods_receipt_item
        UNIQUE (
            receipt_id,
            purchase_order_item_id
        ),

    CONSTRAINT chk_goods_receipt_quantity
        CHECK (quantity_received > 0)
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_purchase_requests_department
    ON purchase_requests(department_id);

CREATE INDEX idx_purchase_requests_status
    ON purchase_requests(status);

CREATE INDEX idx_purchase_request_items_request
    ON purchase_request_items(request_id);

CREATE INDEX idx_purchase_orders_request
    ON purchase_orders(request_id);

CREATE INDEX idx_purchase_orders_supplier
    ON purchase_orders(supplier_id);

CREATE INDEX idx_purchase_orders_status
    ON purchase_orders(status);

CREATE INDEX idx_purchase_order_items_order
    ON purchase_order_items(purchase_order_id);

CREATE INDEX idx_goods_receipts_order
    ON goods_receipts(purchase_order_id);

CREATE INDEX idx_goods_receipts_warehouse
    ON goods_receipts(warehouse_id);