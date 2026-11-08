"""Idempotent schema upgrade against fictional legacy records in disposable SQL."""
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest


def test_upgrade_preserves_three_feature_history_and_baseline(request):
    url = request.config.getoption('--disposable-db-url')
    if not url:
        pytest.skip('Schema upgrade requires the explicit disposable database.')
    schema = 'upgrade_test_' + uuid4().hex
    with psycopg.connect(url) as db:
        db.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        with psycopg.connect(url, row_factory=dict_row, options=f'-csearch_path={schema},public') as db:
            # The existing main schema before the four-feature additions.
            db.execute('''CREATE TABLE profiles (
                profile_id TEXT PRIMARY KEY, condition TEXT NOT NULL,
                baseline_median JSONB, baseline_mad JSONB, created_at TIMESTAMPTZ DEFAULT now());
                CREATE TABLE checkins (
                time TIMESTAMPTZ NOT NULL DEFAULT now(), profile_id TEXT REFERENCES profiles(profile_id),
                pause_fraction DOUBLE PRECISION, longest_internal_gap DOUBLE PRECISION,
                speaking_rate DOUBLE PRECISION, deviation_score DOUBLE PRECISION,
                triggered BOOLEAN, question_text TEXT, patient_said TEXT, note_status TEXT);
                SELECT create_hypertable('checkins', 'time');''')
            median = {'pause_fraction': .2, 'longest_internal_gap': .4, 'speaking_rate': 3.0}
            mad = {'pause_fraction': .1, 'longest_internal_gap': .2, 'speaking_rate': .5}
            db.execute("INSERT INTO profiles(profile_id,condition,baseline_median,baseline_mad) "
                       "VALUES('legacy-fictional','parkinsons',%s,%s)", (Jsonb(median), Jsonb(mad)))
            stamp = db.execute("INSERT INTO checkins(profile_id,pause_fraction,longest_internal_gap,"
                "speaking_rate,deviation_score,triggered,patient_said,note_status) VALUES "
                "('legacy-fictional',.2,.4,3,0,FALSE,'Fictional historical answer','confirmed') RETURNING time").fetchone()['time']
            ddl = (Path(__file__).parents[1] / 'app/api/schema.sql').read_text(encoding='utf-8')
            db.execute(ddl)
            db.execute(ddl)
            profile = db.execute("SELECT * FROM profiles WHERE profile_id='legacy-fictional'").fetchone()
            assert profile['baseline_median'] == median and profile['baseline_mad'] == mad
            assert profile['waveform_baseline'] is None
            row = db.execute('SELECT * FROM checkins WHERE time=%s', (stamp,)).fetchone()
            assert row['patient_said'] == 'Fictional historical answer'
            assert row['note_status'] == 'confirmed' and row['speaking_rate'] == 3
            assert row['mean_speech_segment_duration'] is None and row['feature_scores'] is None
            assert row['waveform_evidence'] is None and row['phrase_evidence'] is None
            assert db.execute('SELECT count(*) AS n FROM patient_reports').fetchone()['n'] == 0
    finally:
        with psycopg.connect(url) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
