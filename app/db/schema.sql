-- SecureVision Database Schema  (Iteration 3)
-- Applied automatically by db/migrations.py → init_db()

-- =====================================================================
-- Enrolled identities
-- =====================================================================
CREATE TABLE IF NOT EXISTS persons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    embedding     BLOB   NOT NULL,           -- np.float32.tobytes()
    embedding_dim INTEGER NOT NULL,           -- 512 for ArcFace
    dtype         TEXT    NOT NULL DEFAULT 'float32',
    created_at    TEXT    NOT NULL             -- ISO 8601 (UTC)
);

-- =====================================================================
-- Per-shot raw embeddings  (ML Integration)
-- =====================================================================
CREATE TABLE IF NOT EXISTS person_embeddings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER NOT NULL,
    embedding     BLOB    NOT NULL,           -- np.float32.tobytes()
    embedding_dim INTEGER NOT NULL,           -- 512 for ArcFace
    dtype         TEXT    NOT NULL DEFAULT 'float32',
    created_at    TEXT    NOT NULL,            -- ISO 8601 (UTC)
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_person_embeddings_person_id
    ON person_embeddings(person_id);

-- =====================================================================
-- Recognition / presence events  (Iteration 3)
-- =====================================================================
CREATE TABLE IF NOT EXISTS events (
    id            TEXT    PRIMARY KEY,         -- UUID-4
    status        TEXT    NOT NULL,            -- 'authorised' | 'unauthorised'
    person_name   TEXT,                        -- display name (NULL ⇒ unknown)
    person_id     INTEGER,                     -- FK → persons.id (NULL ⇒ unknown)
    score         REAL,                        -- best cosine similarity
    bbox_json     TEXT,                        -- JSON bounding box at confirmation
    snapshot_path TEXT,                        -- reserved for Iteration 4
    clip_path     TEXT,                        -- reserved for Iteration 4
    track_key     TEXT,                        -- stable per-entity key (Iteration 11b)
    created_at    TEXT    NOT NULL,            -- ISO 8601 (UTC)
    FOREIGN KEY (person_id) REFERENCES persons(id)
);

CREATE INDEX IF NOT EXISTS idx_events_status     ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- =====================================================================
-- Dashboard admin users  (Iteration 5)
-- =====================================================================
CREATE TABLE IF NOT EXISTS admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,            -- werkzeug.security hash
    created_at    TEXT    NOT NULL             -- ISO 8601 (UTC)
);

-- =====================================================================
-- Alerts  (Iteration 11)
-- =====================================================================
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT    NOT NULL,
    alert_type    TEXT    NOT NULL,
    message       TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,            -- ISO 8601 (UTC)
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
