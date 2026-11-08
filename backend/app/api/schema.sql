CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    condition TEXT NOT NULL CHECK (condition IN ('copd', 'parkinsons')),
    baseline_median JSONB,
    baseline_mad JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS checkins (
    time TIMESTAMPTZ NOT NULL DEFAULT now(),
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    pause_fraction DOUBLE PRECISION,
    longest_internal_gap DOUBLE PRECISION,
    speaking_rate DOUBLE PRECISION,
    deviation_score DOUBLE PRECISION,
    triggered BOOLEAN,
    question_text TEXT,
    patient_said TEXT,
    note_status TEXT
);
SELECT create_hypertable('checkins', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS checkins_profile_time_idx ON checkins (profile_id, time DESC);
