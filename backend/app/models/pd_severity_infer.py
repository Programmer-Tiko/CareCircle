"""Loads the model trained by train_pd_severity.py on CCR and scores a live
sustained-vowel sample. This is a secondary, clearly-labeled research signal --
it does not drive the dialogue trigger. The personal baseline (see
personal_baseline.py) is what decides whether to ask a follow-up question.
"""
from pathlib import Path

import joblib


class VoiceQualityIndex:
    def __init__(self, model_path: Path):
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.features = bundle["features"]

    def score(self, feature_values: dict) -> float:
        missing = [f for f in self.features if f not in feature_values]
        if missing:
            raise ValueError(f"Missing required voice features: {missing}")
        row = [[feature_values[f] for f in self.features]]
        return float(self.model.predict(row)[0])
