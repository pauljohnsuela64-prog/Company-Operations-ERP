-- =========================================================
-- HELP DESK - TICKET HISTORY
-- =========================================================

CREATE TABLE IF NOT EXISTS helpdesk_ticket_history (

    history_id INT AUTO_INCREMENT PRIMARY KEY,

    ticket_id INT NOT NULL,

    action_type VARCHAR(50) NOT NULL,

    old_status VARCHAR(30) NULL,

    new_status VARCHAR(30) NULL,

    details VARCHAR(255) NULL,

    changed_by INT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_helpdesk_history_ticket
        FOREIGN KEY (ticket_id)
        REFERENCES helpdesk_tickets(ticket_id),

    CONSTRAINT fk_helpdesk_history_user
        FOREIGN KEY (changed_by)
        REFERENCES users(user_id)
);