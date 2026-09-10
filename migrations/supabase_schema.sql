-- ============================================================
-- Orderfox / Velzia — PostgreSQL schema for Supabase
-- Generated from SQLAlchemy models (MariaDB → PostgreSQL)
-- ============================================================

-- ── restaurants ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS restaurants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    whatsapp_phone VARCHAR(20) NOT NULL,
    cover_image VARCHAR(255),
    estimated_time INTEGER,
    brand_color VARCHAR(7),
    cuisine_type VARCHAR(30) NOT NULL DEFAULT 'general',
    plan_type VARCHAR(20) NOT NULL DEFAULT 'emprendedor',
    subscription_expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    subscription_state VARCHAR(20) NOT NULL DEFAULT 'active',
    dormant_at TIMESTAMPTZ,
    cancellation_requested_at TIMESTAMPTZ,
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    has_used_trial BOOLEAN NOT NULL DEFAULT FALSE,
    allow_benchmark BOOLEAN NOT NULL DEFAULT TRUE,
    pending_expiry_hours INTEGER NOT NULL DEFAULT 24,
    ntfy_topic VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── users ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
    username VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    clerk_id VARCHAR(100) UNIQUE,
    role VARCHAR(20) NOT NULL DEFAULT 'owner',
    pin_hash VARCHAR(255),
    failed_pin_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_users_clerk_id ON users(clerk_id);

-- ── categories ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    image_url VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── products ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_vegetarian BOOLEAN NOT NULL DEFAULT FALSE,
    is_spicy BOOLEAN NOT NULL DEFAULT FALSE,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    image_url VARCHAR(255),
    image_source VARCHAR(30),
    is_auto_image BOOLEAN NOT NULL DEFAULT FALSE,
    suggested_image_pool TEXT,
    unsplash_source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── modifiers ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS modifiers (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    extra_price INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── tables ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tables (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    qr_code VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── orders ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    table_id INTEGER REFERENCES tables(id) ON DELETE SET NULL,
    order_number VARCHAR(20) NOT NULL,
    customer_name VARCHAR(100),
    customer_phone VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total INTEGER NOT NULL,
    notes TEXT,
    payment_method VARCHAR(20),
    amount_received INTEGER,
    change_due INTEGER,
    paid_at TIMESTAMPTZ,
    ip_address VARCHAR(45),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_ip_address ON orders(ip_address);

-- ── order_items ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
    product_name VARCHAR(100) NOT NULL,
    product_price INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    modifiers_snapshot TEXT,
    subtotal INTEGER NOT NULL
);

-- ── order_events ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_events (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_role VARCHAR(20),
    event_type VARCHAR(30) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON order_events(order_id);

-- ── order_counters ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_counters (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_restaurant_date UNIQUE (restaurant_id, date)
);

-- ── ai_token_wallets ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_token_wallets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    plan_limit INTEGER,
    plan_tokens INTEGER NOT NULL DEFAULT 0,
    extra_tokens INTEGER NOT NULL DEFAULT 0,
    tokens_used_month INTEGER NOT NULL DEFAULT 0,
    reset_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── ai_token_transactions ────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_token_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    amount INTEGER NOT NULL,
    source VARCHAR(50) NOT NULL,
    mp_payment_id VARCHAR(100) UNIQUE,
    description VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── pre_registrations ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pre_registrations (
    id SERIAL PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    selected_plan VARCHAR(20) NOT NULL DEFAULT 'trial',
    whatsapp_phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pre_registrations_email ON pre_registrations(email);

-- ── trial_history ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trial_history (
    id SERIAL PRIMARY KEY,
    email VARCHAR(120),
    whatsapp_phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── expenses ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    description VARCHAR(200) NOT NULL,
    amount INTEGER NOT NULL,
    category VARCHAR(50) DEFAULT 'otros',
    date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── reward_claims ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reward_claims (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    short_code VARCHAR(30) NOT NULL UNIQUE,
    token VARCHAR(36) NOT NULL UNIQUE,
    plan_key VARCHAR(50) NOT NULL,
    rarity VARCHAR(20) NOT NULL,
    reward_type VARCHAR(50) NOT NULL,
    reward_value INTEGER,
    reward_label VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    claimed_at TIMESTAMPTZ,
    claimed_ip VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reward_claims_user_id ON reward_claims(user_id);
CREATE INDEX IF NOT EXISTS idx_reward_claims_short_code ON reward_claims(short_code);
CREATE INDEX IF NOT EXISTS idx_reward_claims_token ON reward_claims(token);

-- ── user_achievements ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_id VARCHAR(50) NOT NULL,
    current_progress INTEGER NOT NULL DEFAULT 1,
    required_progress INTEGER NOT NULL DEFAULT 1,
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_achievement UNIQUE (user_id, achievement_id)
);
CREATE INDEX IF NOT EXISTS idx_user_achievements_user_id ON user_achievements(user_id);
CREATE INDEX IF NOT EXISTS idx_user_achievements_achievement_id ON user_achievements(achievement_id);

-- ── streaks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS streaks (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE UNIQUE,
    renewal_count INTEGER NOT NULL DEFAULT 0,
    highest_tier INTEGER NOT NULL DEFAULT 0,
    last_renewal_at TIMESTAMPTZ,
    last_payment_id VARCHAR(50)
);
CREATE INDEX IF NOT EXISTS idx_streaks_restaurant_id ON streaks(restaurant_id);

-- ── discount_coupons ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS discount_coupons (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    percentage INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reward_claim_id INTEGER REFERENCES reward_claims(id) ON DELETE SET NULL,
    preference_id VARCHAR(100),
    applied_to_payment_id VARCHAR(50),
    reserved_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_discount_coupons_restaurant_id ON discount_coupons(restaurant_id);

-- ── cash_registers ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cash_registers (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    closed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    total_sales INTEGER NOT NULL DEFAULT 0,
    total_orders INTEGER NOT NULL DEFAULT 0,
    avg_ticket INTEGER NOT NULL DEFAULT 0,
    cash_total INTEGER NOT NULL DEFAULT 0,
    cash_orders INTEGER NOT NULL DEFAULT 0,
    nequi_total INTEGER NOT NULL DEFAULT 0,
    nequi_orders INTEGER NOT NULL DEFAULT 0,
    bancolombia_total INTEGER NOT NULL DEFAULT 0,
    bancolombia_orders INTEGER NOT NULL DEFAULT 0,
    card_total INTEGER NOT NULL DEFAULT 0,
    card_orders INTEGER NOT NULL DEFAULT 0,
    cash_change_total INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_restaurant_period_start UNIQUE (restaurant_id, period_start)
);
CREATE INDEX IF NOT EXISTS idx_cash_registers_restaurant_id ON cash_registers(restaurant_id);

-- ── copilot_conversations ────────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_conversations (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source VARCHAR(30) NOT NULL DEFAULT 'insights',
    title VARCHAR(200),
    prompt_version VARCHAR(10) DEFAULT 'v1.0',
    model VARCHAR(50) DEFAULT 'deepseek-v4-flash',
    analysis_active BOOLEAN NOT NULL DEFAULT FALSE,
    follow_up_count INTEGER NOT NULL DEFAULT 0,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_copilot_conversations_source ON copilot_conversations(source);

-- ── copilot_messages ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES copilot_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── copilot_business_events ──────────────────────────────────
CREATE TABLE IF NOT EXISTS copilot_business_events (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    kind VARCHAR(50) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 0,
    title VARCHAR(200) NOT NULL,
    preview VARCHAR(300) NOT NULL,
    template_key VARCHAR(50) NOT NULL,
    template_data TEXT,
    conversation_id INTEGER REFERENCES copilot_conversations(id) ON DELETE SET NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    consumed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_copilot_business_events_restaurant_id ON copilot_business_events(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_copilot_business_events_kind ON copilot_business_events(kind);
CREATE INDEX IF NOT EXISTS idx_copilot_business_events_priority ON copilot_business_events(priority);
CREATE INDEX IF NOT EXISTS idx_copilot_business_events_active ON copilot_business_events(active);

-- ── ai_llm_calls ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_llm_calls (
    id SERIAL PRIMARY KEY,
    source VARCHAR(30) NOT NULL,
    conversation_id INTEGER REFERENCES copilot_conversations(id) ON DELETE SET NULL,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    model VARCHAR(50) NOT NULL,
    input_tokens_est INTEGER NOT NULL DEFAULT 0,
    output_tokens_est INTEGER NOT NULL DEFAULT 0,
    execution_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_llm_calls_source ON ai_llm_calls(source);
CREATE INDEX IF NOT EXISTS idx_ai_llm_calls_conversation_id ON ai_llm_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_ai_llm_calls_restaurant_id ON ai_llm_calls(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_ai_llm_calls_created_at ON ai_llm_calls(created_at);

-- ── platform_benchmarks ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_benchmarks (
    id SERIAL PRIMARY KEY,
    cohort VARCHAR(30) NOT NULL UNIQUE,
    restaurant_count INTEGER NOT NULL DEFAULT 0,
    period_days INTEGER NOT NULL DEFAULT 30,
    metrics_json TEXT NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_benchmarks_cohort ON platform_benchmarks(cohort);
