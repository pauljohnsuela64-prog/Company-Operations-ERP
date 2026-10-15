-- =========================================================
-- IT ASSET ASSIGNMENT HISTORY
-- =========================================================

CREATE TABLE IF NOT EXISTS it_asset_assignments (

    assignment_id INT AUTO_INCREMENT PRIMARY KEY,

    asset_id INT NOT NULL,

    employee_id INT NOT NULL,

    department_id INT NULL,

    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    returned_at DATETIME NULL,

    assigned_by INT NOT NULL,

    returned_by INT NULL,

    notes VARCHAR(255) NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_it_assignment_asset
        FOREIGN KEY (asset_id)
        REFERENCES it_assets(asset_id),

    CONSTRAINT fk_it_assignment_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id),

    CONSTRAINT fk_it_assignment_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),

    CONSTRAINT fk_it_assignment_assigned_by
        FOREIGN KEY (assigned_by)
        REFERENCES users(user_id),

    CONSTRAINT fk_it_assignment_returned_by
        FOREIGN KEY (returned_by)
        REFERENCES users(user_id)
);