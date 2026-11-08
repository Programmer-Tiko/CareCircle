"""Research evaluation guards: participant isolation and unavailable measurements."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = spec_from_file_location('multisignal', Path(__file__).parents[1] / 'scripts' / 'ccr_multisignal_ablation.py')
module = module_from_spec(spec)
spec.loader.exec_module(module)


def frame():
    rng = np.random.default_rng(2)
    rows=[]
    for dataset in ['english', 'italian']:
        for subject in range(20):
            for take in range(2):
                row={'path':f'{dataset}/{subject}/{take}.wav', 'subject_id':f'{dataset}_{subject}',
                     'label':subject % 2, 'dataset':dataset}
                row.update({key:float(rng.normal()+row['label']) for key in module.TIMING+module.PROSODY})
                rows.append(row)
    return pd.DataFrame(rows)


def test_subject_overlap_across_datasets_is_rejected():
    data=frame()
    data.loc[(data.dataset=='italian') & (data.subject_id=='italian_0'), 'subject_id']='english_0'
    with pytest.raises(ValueError, match='overlaps datasets'):
        module.participant_table(data)


def test_repeated_takes_are_one_participant_and_folds_are_disjoint():
    aggregated=module.participant_table(frame())
    assert len(aggregated)==40
    for train,test in module.group_folds(aggregated):
        assert not set(aggregated.iloc[train].subject_id) & set(aggregated.iloc[test].subject_id)


def test_missing_rate_is_excluded_and_other_missing_features_are_imputed():
    data=frame()
    data['speaking_rate']=np.nan
    data.loc[::7, 'f0_spread_semitones']=np.nan
    result=module.evaluate(data, permutations=1)
    assert result['excluded_all_missing_features']==['speaking_rate']
    assert result['participants']==40
    for method in ['timing','prosody','combined']:
        assert 'speaking_rate' not in result['ablations'][method]['features']
        assert len(result['ablations'][method]['cross_dataset'])==2
        for outcome in result['ablations'][method]['cross_dataset'].values():
            assert 0 <= outcome['auc'] <= 1
            assert outcome['permutation_p'] in [.5,1.]


def test_conflicting_labels_and_duplicate_paths_rejected():
    data=frame()
    data.loc[0,'label']=1-data.loc[1,'label']
    with pytest.raises(ValueError,match='conflicting labels'):
        module.participant_table(data)
    data=frame()
    data.loc[0,'path']=data.loc[1,'path']
    with pytest.raises(ValueError,match='Duplicate recording'):
        module.participant_table(data)


def test_extract_does_not_guess_unknown_passage_count(tmp_path, monkeypatch):
    from app import pipeline
    from app.audio import prosody_features
    manifest=tmp_path/'manifest.csv'
    pd.DataFrame([{'path':'record.wav','subject_id':'s1','label':1,'dataset':'study'}]).to_csv(manifest,index=False)
    import soundfile as sf
    sf.write(tmp_path/'record.wav', np.zeros(1600), 16000)
    def timing(path, count):
        assert count==1  # discarded inverse-duration placeholder, never 41
        return {'pause_fraction':.2,'longest_internal_gap':.4,'speaking_rate':999.,'mean_speech_segment_duration':2.}
    monkeypatch.setattr(pipeline,'build_take_from_audio',timing)
    monkeypatch.setattr(prosody_features,'extract_prosody_features',lambda path: {
        'metrics':{key:None for key in module.PROSODY+module.DIAGNOSTICS},'quality_flags':['insufficient_voicing']})
    output=tmp_path/'features.csv'
    module.extract(manifest,output)
    result=pd.read_csv(output)
    assert pd.isna(result.loc[0,'speaking_rate'])
    assert result.loc[0,'pause_fraction']==.2
    assert pd.isna(result.loc[0,'f0_spread_semitones'])
    assert 'UnavailablePassageCount' in output.with_suffix('.failures.json').read_text()


def test_preflight_rejects_inaccessible_audio_before_extraction(tmp_path):
    data = frame().iloc[:1]
    with pytest.raises(ValueError, match='Audio preflight failed for 1/1'):
        module.preflight_audio(data, tmp_path/'manifest.csv')


def test_evaluation_rejects_total_extraction_failure():
    data = frame()
    data[module.TIMING + module.PROSODY] = np.nan
    with pytest.raises(ValueError, match='without any acoustic measurements'):
        module.evaluate(data)
