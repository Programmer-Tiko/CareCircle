"""Experimental personal waveform references, separate from the timing trigger.

Differences are descriptive, not disease scores or calibrated alert thresholds.
No z-score is added to the timing Euclidean norm. Require three usable takes
per metric, preserving unavailable observations as unavailable rather than zero.
"""
import math
from statistics import median

METRICS={'f0_spread_semitones':'semitones','voiced_energy_spread_db':'dB'}


def fit_observation_reference(evidence):
    features={}
    for key,units in METRICS.items():
        values=[item['metrics'][key] for item in evidence
                if not item.get('quality_flags') and isinstance(item.get('metrics',{}).get(key),(int,float))
                and math.isfinite(item['metrics'][key])]
        if len(values)>=3:
            center=median(values)
            features[key]={'median':center,'scaled_mad':1.4826*median(abs(v-center) for v in values),
                           'n_reference_takes':len(values),'units':units}
    return {'experimental':True,'features':features,'method':'personal median; descriptive differences only',
            'available':bool(features)}


def compare_observations(evidence,reference):
    if not reference or not reference.get('available'):
        return {'available':False,'reason':'No usable experimental reference. Enroll a new profile with experimental observations enabled.'}
    result={'available':False,'experimental':True,'contributes_to_trigger':False}
    for key,base in reference.get('features',{}).items():
        value=evidence.get('metrics',{}).get(key)
        if value is None or not math.isfinite(value):continue
        result[key]={'reference_median':base['median'],'difference':value-base['median'],
                     'n_reference_takes':base['n_reference_takes'],'units':base['units']}
        result['available']=True
    if not result['available']:result['reason']='This recording has no usable waveform measurement for personal comparison.'
    return result
