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

-- Conversations are opt-in; legacy answer/confirm endpoints retain their contract.
CREATE TABLE IF NOT EXISTS conversations (
    session_id UUID PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    checkin_time TIMESTAMPTZ NOT NULL,
    measured JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'complete', 'abstained', 'confirmed')),
    note JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    UNIQUE (profile_id, checkin_time)
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES conversations(session_id),
    ordinal INTEGER NOT NULL,
    question JSONB NOT NULL,
    asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answer TEXT,
    answered_at TIMESTAMPTZ,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    submission_id UUID,
    selection JSONB,
    UNIQUE (session_id, ordinal),
    UNIQUE (session_id, submission_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS conversation_one_pending_turn
    ON conversation_turns (session_id) WHERE answered_at IS NULL;
