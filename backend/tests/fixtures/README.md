# Test fixtures

`speech_chunk.wav` — a 1-second clip of real speech, used only so Silero
VAD (a neural model trained on real speech) actually detects it as speech
in pipeline tests; a synthetic sine tone is correctly rejected by VAD and
can't stand in for it.

Source: MDVR-KCL ("Mobile Device Voice Recordings at King's College
London"), https://zenodo.org/records/2867216, licensed CC-BY-4.0.
Extracted from `ReadText/HC/ID00_hc_0_0_0.wav`, seconds 70.6-71.6.
