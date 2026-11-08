from app.audio.observation_reference import fit_observation_reference,compare_observations


def take(pitch,energy,flags=()):
    return {'metrics':{'f0_spread_semitones':pitch,'voiced_energy_spread_db':energy},'quality_flags':list(flags)}


def test_uses_three_valid_takes_not_zero_filled_missing():
    ref=fit_observation_reference([take(2,5),take(4,7),take(3,6),take(None,None),take(999,999,['clipping'])])
    assert ref['features']['f0_spread_semitones']['median']==3
    compared=compare_observations(take(3.5,5),ref)
    assert compared['f0_spread_semitones']['difference']==.5
    assert compared['voiced_energy_spread_db']['difference']==-1
    assert not compared['contributes_to_trigger']


def test_no_reference_or_bad_recording_stays_unavailable():
    ref=fit_observation_reference([take(2,3),take(4,5)])
    assert not compare_observations(take(2,3),ref)['available']
    ref=fit_observation_reference([take(2,3),take(4,5),take(3,4)])
    assert not compare_observations(take(None,None),ref)['available']
