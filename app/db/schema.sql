-- SecureVision Database Schema  (Iteration 2)
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
-- Recognition / alert events  (Iteration 3+ populates this)
-- =====================================================================
CREATE TABLE IF NOT EXISTS events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id        INTEGER,
    event_type       TEXT NOT NULL,
    confidence       REAL,
    similarity_score REAL,
    snapshot_path    TEXT,
    created_at       TEXT NOT NULL,            -- ISO 8601 (UTC)
    FOREIGN KEY (person_id) REFERENCES persons(id)
);

CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_person_id  ON events(person_id);
