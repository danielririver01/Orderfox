-- Migration: add copilot_business_events table
-- Run: mysql -u root -p orderfox < migrations/raw_add_business_events.sql

CREATE TABLE IF NOT EXISTS copilot_business_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id INT NOT NULL,
    kind VARCHAR(50) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 0,
    title VARCHAR(200) NOT NULL,
    preview VARCHAR(300) NOT NULL,
    template_key VARCHAR(50) NOT NULL,
    template_data TEXT,
    conversation_id INT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME,
    consumed_at DATETIME,
    dismissed_at DATETIME,
    INDEX idx_restaurant_active (restaurant_id, active),
    INDEX idx_kind (kind),
    INDEX idx_priority (priority),
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES copilot_conversations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
