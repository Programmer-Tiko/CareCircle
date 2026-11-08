"""Research-only, participant-safe timing/prosody ablation for CCR.

Extract a CSV manifest into reusable features, then evaluate timing, prosody,
and their union with preprocessing fit separately inside each training fold.
No result is wired into the personal-baseline trigger or patient-facing notes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TIMING = ['pause_fraction', 'longest_internal_gap', 'speaking_rate', 'mean_speech_segment_duration']
# Keep in sync with app/audio/prosody_features.py. These are candidate acoustic
# measurements, not established disease/severity indicators.
PROSODY = ['f0_spread_semitones', 'voiced_energy_spread_db']
DIAGNOSTICS = ['voiced_fraction', 'pitch_octave_jump_fraction']
METADATA = ['path', 'subject_id', 'label', 'dataset']


def validate_metadata(frame):
    missing = set(METADATA) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing manifest columns: {sorted(missing)}')
    if frame[METADATA].isna().any().any():
        raise ValueError('Manifest metadata must not be missing.')
    if not set(frame['label'].unique()) <= {0, 1}:
        raise ValueError('Labels must be 0=control or 1=PD.')
    for key in ('subject_id', 'dataset', 'path'):
        if frame[key].astype(str).str.strip().eq('').any():
            raise ValueError(f'{key} must not be blank.')
    # IDs must identify actual people globally; don't namespace automatically
    # and accidentally hide a participant appearing in both train and holdout.
    grouped = frame.groupby('subject_id')
    if (grouped['label'].nunique() != 1).any():
        raise ValueError('A participant has conflicting labels.')
    if (grouped['dataset'].nunique() != 1).any():
        raise ValueError('Participant overlaps datasets: cross-dataset leakage.')
    if frame['path'].duplicated().any():
        raise ValueError('Duplicate recording paths could disguise participant overlap.')



def preflight_audio(frame, manifest_path):
    """Fail on the execution node before fitting/extracting inaccessible inputs."""
    import soundfile as sf
    bad = []
    for raw in frame['path']:
        path = Path(str(raw))
        if not path.is_absolute():
            path = manifest_path.parent / path
        try:
            info = sf.info(path)
            if info.frames <= 0:
                raise ValueError('empty recording')
        except (OSError, ValueError, sf.LibsndfileError) as exc:
            bad.append(f'{path}: {exc}')
    if bad:
        raise ValueError(f'Audio preflight failed for {len(bad)}/{len(frame)} recordings on this node. '
                         'Stage inputs on shared storage or the correct local scratch. First failures: '
                         + '; '.join(bad[:3]))


def extract(manifest_path, output, syllable_count=None, perturbations=False):
    from app.pipeline import build_take_from_audio
    from app.audio.prosody_features import extract_prosody_features
    frame = pd.read_csv(manifest_path)
    validate_metadata(frame)
    preflight_audio(frame, manifest_path)
    records, failures, robustness = [], [], []
    rng = np.random.default_rng(0)
    for row in frame.to_dict('records'):
        path = Path(str(row['path']))
        if not path.is_absolute():
            path = manifest_path.parent / path
        record = {key: row[key] for key in METADATA}
        # Each branch reports failure separately. No missing acoustic value is
        # silently replaced by zero; fold-local imputation is explicit later.
        count = row.get('passage_syllable_count', syllable_count)
        count_available = count is not None and not pd.isna(count)
        try:
            if count_available and (int(count) != count or count <= 0):
                raise ValueError('passage_syllable_count must be a positive integer.')
            # A count of one is used only to obtain the other timing metrics.
            # Its inverse-duration rate is discarded, never called syllables/s.
            record.update(build_take_from_audio(str(path), int(count) if count_available else 1))
            if not count_available:
                record['speaking_rate'] = None
                failures.append({key: record[key] for key in METADATA} | {
                    'stage':'speaking_rate', 'error':'UnavailablePassageCount',
                    'detail':'Actual passage syllable count absent; rate deliberately unavailable.'})
        except Exception as exc:
            failures.append({key: record[key] for key in METADATA} | {
                'stage': 'timing', 'error': type(exc).__name__, 'detail': str(exc)})
        try:
            result = extract_prosody_features(str(path))
            record.update({key: result['metrics'].get(key) for key in PROSODY + DIAGNOSTICS})
            record['prosody_quality_flags'] = json.dumps(result.get('quality_flags', []))
            if perturbations:
                import soundfile as sf
                from tempfile import TemporaryDirectory
                waveform, sr = sf.read(path, dtype='float64', always_2d=True)
                rms = float(np.sqrt(np.mean(waveform ** 2)))
                variants = {'gain_half': waveform * .5,
                            'noise_30db': waveform + rng.normal(0, rms / (10 ** (30 / 20)), waveform.shape)}
                with TemporaryDirectory(prefix='cadence-robustness-') as tmp:
                    for variant, audio in variants.items():
                        changed_path = Path(tmp) / (variant + '.wav')
                        sf.write(changed_path, audio, sr, subtype='FLOAT')
                        changed = extract_prosody_features(str(changed_path))
                        item = {key: record[key] for key in METADATA} | {'variant': variant,
                            'quality_flags': json.dumps(changed['quality_flags'])}
                        for key in PROSODY + DIAGNOSTICS:
                            original, altered = result['metrics'].get(key), changed['metrics'].get(key)
                            item[key] = altered
                            item[key + '_delta'] = altered - original if original is not None and altered is not None else None
                        robustness.append(item)
        except Exception as exc:
            failures.append({key: record[key] for key in METADATA} | {
                'stage': 'prosody', 'error': type(exc).__name__, 'detail': str(exc)})
        records.append(record)
    result = pd.DataFrame(records).reindex(columns=METADATA + TIMING + PROSODY + DIAGNOSTICS + ['prosody_quality_flags'])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    if perturbations:
        pd.DataFrame(robustness).to_csv(output.with_suffix('.robustness.csv'), index=False)
    output.with_suffix('.failures.json').write_text(json.dumps(failures, indent=2) + '\n')
    return {'recordings': len(records), 'stage_failures': len(failures), 'output': str(output)}


def participant_table(frame):
    validate_metadata(frame)
    required = TIMING + PROSODY
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing feature columns: {sorted(missing)}; extraction failures must be explicit NaN values.')
    clean = frame.copy()
    for key in required:
        clean[key] = pd.to_numeric(clean[key], errors='raise')
        if np.isinf(clean[key].to_numpy()).any():
            raise ValueError(f'Infinite measurement in {key}; use missing values with an extraction failure record.')
    # One row and one vote per participant. Repeated recordings/chunks never
    # enter different folds and cannot give a heavily-recorded person more weight.
    subjects = clean.groupby('subject_id', sort=True)[required].median()
    subjects['label'] = clean.groupby('subject_id')['label'].first()
    subjects['dataset'] = clean.groupby('subject_id')['dataset'].first()
    return subjects.reset_index()


def pipeline():
    return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                         StandardScaler(), LogisticRegression(C=.1, max_iter=2000, random_state=0))


def group_folds(frame, seed=0):
    y = frame['label'].to_numpy()
    counts = frame.groupby('label')['subject_id'].nunique()
    if len(counts) != 2 or counts.min() < 2:
        raise ValueError('Each class needs at least two independent participants for cross-validation.')
    split = StratifiedGroupKFold(n_splits=min(5, int(counts.min())), shuffle=True, random_state=seed)
    folds = []
    for train, test in split.split(np.zeros((len(y), 1)), y, frame['subject_id']):
        assert not set(frame.iloc[train]['subject_id']) & set(frame.iloc[test]['subject_id'])
        if len(np.unique(y[train])) != 2 or len(np.unique(y[test])) != 2:
            raise ValueError('A grouped fold lacks a class; increase sample size or revise prespecified split.')
        folds.append((train, test))
    return folds


def oof_auc(frame, columns, seed=0):
    X, y = frame[columns], frame['label'].to_numpy()
    predictions = np.empty(len(frame))
    audit = []
    for train, test in group_folds(frame, seed):
        model = pipeline().fit(X.iloc[train], y[train])
        predictions[test] = model.predict_proba(X.iloc[test])[:, 1]
        audit.append({'train_subjects': frame.iloc[train]['subject_id'].astype(str).tolist(),
                      'test_subjects': frame.iloc[test]['subject_id'].astype(str).tolist()})
    return float(roc_auc_score(y, predictions)), audit


def evaluate(features, permutations=0, seed=0):
    frame = participant_table(features)
    datasets = sorted(frame['dataset'].unique())
    if len(datasets) < 2:
        raise ValueError('Provide at least two datasets for a frozen cross-dataset holdout.')
    if frame[TIMING + PROSODY].isna().all(axis=1).any():
        raise ValueError('Participants without any acoustic measurements cannot be evaluated; inspect extraction failures.')
    usable_timing = [key for key in TIMING if not frame[key].isna().all()]
    usable_prosody = [key for key in PROSODY if not frame[key].isna().all()]
    report = {'excluded_all_missing_features':[key for key in TIMING + PROSODY if frame[key].isna().all()],
              'scope': 'exploratory cross-sectional cohort classification, not personal monitoring validation',
              'participants': len(frame), 'recordings': len(features), 'datasets': datasets,
              'aggregation': 'participant median before splitting; one vote per participant',
              'missing_fraction': features[TIMING + PROSODY].isna().mean().to_dict(),
              'missing_fraction_by_cohort_label': {f'{dataset}/label={label}': subset[TIMING + PROSODY].isna().mean().to_dict()
                  for (dataset,label), subset in features.groupby(['dataset','label'])},
              'seed': seed, 'permutations': permutations, 'ablations': {}}
    if 'prosody_quality_flags' in features:
        report['quality_flag_counts'] = {}
        for (dataset, label), subset in features.groupby(['dataset','label']):
            counts = {}
            for raw in subset['prosody_quality_flags'].dropna():
                for flag in json.loads(raw):
                    counts[flag] = counts.get(flag, 0) + 1
            report['quality_flag_counts'][f'{dataset}/label={label}'] = counts
    for name, columns in {'timing': usable_timing, 'prosody': usable_prosody, 'combined': usable_timing + usable_prosody}.items():
        rng = np.random.default_rng(seed)
        if not columns:
            report['ablations'][name] = {'error':'All measurements unavailable.'}
            continue
        result = {'features': columns, 'within_dataset': {}, 'cross_dataset': {}}
        for dataset in datasets:
            subset = frame[frame['dataset'] == dataset].reset_index(drop=True)
            try:
                auc, audit = oof_auc(subset, columns, seed)
                item = {'auc': auc, 'participants': len(subset), 'folds': audit}
                if permutations:
                    null = []
                    for _ in range(permutations):
                        shuffled = subset.copy()
                        shuffled['label'] = rng.permutation(shuffled['label'].to_numpy())
                        null.append(oof_auc(shuffled, columns, seed)[0])
                    item['permutation_p'] = (1 + sum(v >= auc for v in null)) / (permutations + 1)
                    item['permutation_auc'] = null
                result['within_dataset'][dataset] = item
            except ValueError as exc:
                result['within_dataset'][dataset] = {'error': str(exc)}
        for source in datasets:
            train = frame[frame['dataset'] == source]
            if train['label'].nunique() != 2:
                continue
            for target in datasets:
                if target == source:
                    continue
                test = frame[frame['dataset'] == target]
                assert not set(train['subject_id']) & set(test['subject_id'])
                if test['label'].nunique() != 2:
                    result['cross_dataset'][source + '->' + target] = {'error': 'Holdout lacks a class.'}
                    continue
                model = pipeline().fit(train[columns], train['label'])
                auc = float(roc_auc_score(test['label'], model.predict_proba(test[columns])[:, 1]))
                item = {'auc': auc, 'train_participants': len(train), 'test_participants': len(test)}
                if permutations:
                    null = []
                    for _ in range(permutations):
                        # Only training labels are shuffled; target labels remain untouched.
                        model = pipeline().fit(train[columns], rng.permutation(train['label'].to_numpy()))
                        null.append(float(roc_auc_score(test['label'], model.predict_proba(test[columns])[:, 1])))
                    item['permutation_p'] = (1 + sum(v >= auc for v in null)) / (permutations + 1)
                    item['permutation_auc'] = null
                result['cross_dataset'][source + '->' + target] = item
        report['ablations'][name] = result
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    extraction = sub.add_parser('extract')
    extraction.add_argument('--manifest', required=True, type=Path)
    extraction.add_argument('--output', required=True, type=Path)
    extraction.add_argument('--syllable-count', type=int)
    extraction.add_argument('--perturbations', action='store_true', help='Also record paired gain/noise robustness, separate from training data.')
    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('--features', required=True, type=Path)
    evaluation.add_argument('--output', required=True, type=Path)
    evaluation.add_argument('--permutations', type=int, default=0)
    evaluation.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'extract':
        print(json.dumps(extract(args.manifest, args.output, args.syllable_count, args.perturbations), indent=2))
    else:
        if args.permutations < 0:
            parser.error('--permutations must be nonnegative')
        result = evaluate(pd.read_csv(args.features), args.permutations, args.seed)
        result['features_sha256'] = hashlib.sha256(args.features.read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        print(json.dumps({'participants': result['participants'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
