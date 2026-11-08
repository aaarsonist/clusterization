-- =============================================================================
-- Схема базы данных программного средства сегментации клиентов методами
-- кластерного анализа в целях персонализации лояльности.
-- СУБД PostgreSQL 17. Отношения нормализованы до третьей нормальной формы.
-- Персональные данные клиентов (телефон, e-mail) хранятся в зашифрованном виде
-- (AES-256-GCM), поиск выполняется по хеш-индексам HMAC-SHA-256.
-- =============================================================================

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(32)  NOT NULL CHECK (role IN ('маркетолог', 'администратор')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMPTZ
);
COMMENT ON TABLE users IS 'Учетные записи сотрудников с ролевой моделью доступа';
COMMENT ON COLUMN users.password_hash IS 'Хеш пароля bcrypt (12 раундов)';

CREATE TABLE clients (
    id              BIGSERIAL PRIMARY KEY,
    external_code   VARCHAR(64)  NOT NULL UNIQUE,
    full_name       VARCHAR(255) NOT NULL,
    phone_enc       TEXT         NOT NULL,
    phone_hash      CHAR(64)     NOT NULL UNIQUE,
    phone_tail_hash CHAR(64)     NOT NULL,
    email_enc       TEXT,
    email_hash      CHAR(64)     UNIQUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE clients IS 'Анкеты клиентов программы лояльности';
COMMENT ON COLUMN clients.phone_enc IS 'Телефон в формате E.164, зашифрованный AES-256-GCM';
COMMENT ON COLUMN clients.phone_hash IS 'HMAC-SHA-256 полного номера (поиск и уникальность)';
COMMENT ON COLUMN clients.phone_tail_hash IS 'HMAC-SHA-256 последних 7 цифр номера (поиск на кассе)';
CREATE INDEX idx_clients_phone_tail ON clients (phone_tail_hash);

CREATE TABLE transactions (
    id               BIGSERIAL PRIMARY KEY,
    client_id        BIGINT        NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    transaction_date TIMESTAMPTZ   NOT NULL,
    total_amount     NUMERIC(12,2) NOT NULL CHECK (total_amount >= 0),
    discount_amount  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0 AND discount_amount <= total_amount),
    status           VARCHAR(16)   NOT NULL DEFAULT 'проведен' CHECK (status IN ('проведен', 'отменен'))
);
COMMENT ON TABLE transactions IS 'Кассовые чеки; в RFM-анализ включаются только проведенные';
CREATE INDEX idx_transactions_client_date ON transactions (client_id, transaction_date);
CREATE INDEX idx_transactions_date ON transactions (transaction_date);

CREATE TABLE segmentation_runs (
    id                 BIGSERIAL PRIMARY KEY,
    status             VARCHAR(16) NOT NULL DEFAULT 'черновик'
                       CHECK (status IN ('черновик', 'расчет', 'рассчитан', 'ошибка', 'утвержден', 'архивный')),
    days_period        INT         NOT NULL CHECK (days_period BETWEEN 30 AND 730),
    reference_date     TIMESTAMPTZ NOT NULL,
    target_k           SMALLINT    CHECK (target_k BETWEEN 2 AND 8),
    algorithm          VARCHAR(16) CHECK (algorithm IN ('kmeans', 'agglomerative', 'dbscan')),
    scaler_params      JSONB,
    metrics            JSONB,
    xai                JSONB,
    error_message      TEXT,
    created_by_user_id BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at       TIMESTAMPTZ,
    approved_at        TIMESTAMPTZ
);
COMMENT ON TABLE segmentation_runs IS 'Реестр прогонов (версий) моделей сегментации и их жизненный цикл';
COMMENT ON COLUMN segmentation_runs.scaler_params IS 'Параметры стандартизации признаков (средние, отклонения)';
COMMENT ON COLUMN segmentation_runs.metrics IS 'Сводка метрик и профили кластеров трех моделей';
COMMENT ON COLUMN segmentation_runs.xai IS 'Данные объяснения: метод локтя, k-NN, дендрограмма, вердикт';
CREATE UNIQUE INDEX uq_runs_single_approved ON segmentation_runs (status) WHERE status = 'утвержден';

CREATE TABLE client_features (
    run_id              BIGINT        NOT NULL REFERENCES segmentation_runs (id) ON DELETE CASCADE,
    client_id           BIGINT        NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    recency_days        NUMERIC(8,1)  NOT NULL,
    frequency           INT           NOT NULL,
    monetary            NUMERIC(14,2) NOT NULL,
    pca_x               REAL,
    pca_y               REAL,
    label_kmeans        SMALLINT,
    label_agglomerative SMALLINT,
    label_dbscan        SMALLINT,
    PRIMARY KEY (run_id, client_id)
);
COMMENT ON TABLE client_features IS 'Матрица признаков RFM прогона, координаты PCA и метки трех моделей';

CREATE TABLE clusters (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT        NOT NULL REFERENCES segmentation_runs (id) ON DELETE CASCADE,
    cluster_no       SMALLINT      NOT NULL,
    segment_code     VARCHAR(16)   NOT NULL CHECK (segment_code IN ('vip', 'churn', 'newbie', 'bargain', 'regular', 'noise')),
    cluster_label    VARCHAR(64)   NOT NULL,
    description      TEXT          NOT NULL DEFAULT '',
    silhouette_score NUMERIC(5,4)  CHECK (silhouette_score BETWEEN -1 AND 1),
    r_center         NUMERIC(10,2) NOT NULL,
    f_center         NUMERIC(10,2) NOT NULL,
    m_center         NUMERIC(14,2) NOT NULL,
    z_recency        DOUBLE PRECISION,
    z_frequency      DOUBLE PRECISION,
    z_monetary       DOUBLE PRECISION,
    client_count     INT           NOT NULL CHECK (client_count >= 0),
    UNIQUE (run_id, cluster_no)
);
COMMENT ON TABLE clusters IS 'Сегменты утвержденной модели: центроиды RFM и стандартизованные центроиды';
COMMENT ON COLUMN clusters.silhouette_score IS 'Средний коэффициент силуэта объектов данного кластера';

CREATE TABLE segmentation_snapshots (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             BIGINT      NOT NULL REFERENCES segmentation_runs (id) ON DELETE CASCADE,
    kind               VARCHAR(2)  NOT NULL CHECK (kind IN ('T0', 'T1')),
    reference_date     TIMESTAMPTZ NOT NULL,
    created_by_user_id BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE segmentation_snapshots IS 'Срезы распределения клиентов: T0 при утверждении, T1 при мониторинге';
CREATE INDEX idx_snapshots_run ON segmentation_snapshots (run_id, created_at);

CREATE TABLE client_cluster_history (
    snapshot_id BIGINT NOT NULL REFERENCES segmentation_snapshots (id) ON DELETE CASCADE,
    client_id   BIGINT NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    cluster_id  BIGINT NOT NULL REFERENCES clusters (id) ON DELETE CASCADE,
    PRIMARY KEY (snapshot_id, client_id)
);
COMMENT ON TABLE client_cluster_history IS 'Принадлежность клиентов кластерам в каждом срезе';
CREATE INDEX idx_history_cluster ON client_cluster_history (cluster_id);

CREATE TABLE client_cluster_mapping (
    client_id  BIGINT      PRIMARY KEY REFERENCES clients (id) ON DELETE CASCADE,
    cluster_id BIGINT      NOT NULL REFERENCES clusters (id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE client_cluster_mapping IS 'Актуальный сегмент каждого клиента (последний срез)';
CREATE INDEX idx_mapping_cluster ON client_cluster_mapping (cluster_id);

CREATE TABLE loyalty_rules (
    id                 BIGSERIAL PRIMARY KEY,
    cluster_id         BIGINT        REFERENCES clusters (id) ON DELETE SET NULL,
    created_by_user_id BIGINT        REFERENCES users (id) ON DELETE SET NULL,
    rule_name          VARCHAR(255)  NOT NULL,
    reward_type        VARCHAR(16)   NOT NULL CHECK (reward_type IN ('скидка', 'баллы', 'кешбэк')),
    reward_value       NUMERIC(10,2) NOT NULL CHECK (reward_value > 0),
    min_check_amount   NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (min_check_amount >= 0),
    days_valid         INT           NOT NULL CHECK (days_valid > 0),
    is_active          BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_percent_reward CHECK (reward_type = 'баллы' OR reward_value <= 100)
);
COMMENT ON TABLE loyalty_rules IS 'Персонализированные правила лояльности (NULL в cluster_id - общее правило)';
CREATE INDEX idx_rules_cluster ON loyalty_rules (cluster_id);
CREATE INDEX idx_rules_active ON loyalty_rules (is_active);

CREATE TABLE loyalty_rule_custom_clients (
    rule_id     BIGINT      NOT NULL REFERENCES loyalty_rules (id) ON DELETE CASCADE,
    client_id   BIGINT      NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    is_excluded BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rule_id, client_id)
);
COMMENT ON TABLE loyalty_rule_custom_clients IS 'Ручные включения (FALSE) и исключения (TRUE) клиентов из аудитории правила';
CREATE INDEX idx_custom_client ON loyalty_rule_custom_clients (client_id);

CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    event_time  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id     BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    username    VARCHAR(64),
    action      VARCHAR(64) NOT NULL,
    object_type VARCHAR(64),
    object_id   VARCHAR(64),
    success     BOOLEAN     NOT NULL DEFAULT TRUE,
    ip_address  VARCHAR(45),
    details     JSONB       NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON TABLE audit_log IS 'Журнал аудита действий пользователей и системных событий';
CREATE INDEX idx_audit_time ON audit_log (event_time DESC);
CREATE INDEX idx_audit_action ON audit_log (action);

CREATE TABLE backup_settings (
    id                 SMALLINT    PRIMARY KEY CHECK (id = 1),
    enabled            BOOLEAN     NOT NULL DEFAULT TRUE,
    run_hour           SMALLINT    NOT NULL DEFAULT 2 CHECK (run_hour BETWEEN 0 AND 23),
    retention_count    SMALLINT    NOT NULL DEFAULT 14 CHECK (retention_count BETWEEN 1 AND 90),
    updated_by_user_id BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE backup_settings IS 'Параметры автоматического резервного копирования (единственная строка)';
INSERT INTO backup_settings (id) VALUES (1);
