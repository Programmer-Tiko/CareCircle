VoiceGuard AI
Personalized Voice Check-ins • Adaptive Conversations • Family Care Alerts
UB Hacking 2026 | Three-Person Team | Research / Demo Prototype
Pitch: VoiceGuard lets an older adult talk naturally to a simple, friendly app. The app compares measurable speech features to that person's reference recordings, asks a small number of relevant follow-up questions, and—when permission has been provided—creates a care notification for a family member. It includes links to relevant medical research without claiming to diagnose a disease.

Why VoiceGuard?
Older adults may find fixed, yes/no checklists frustrating. VoiceGuard uses natural, open-ended questions and a familiar, clearly identified AI companion to make daily check-ins easier. A relative can see check-in status and receive an alert without requesting or initiating the analysis.

Two experiences / one backend:
- Senior mode: very large Talk to VoiceGuard, Call Family, I Need Help buttons; audio guidance; short, natural conversations.
- Family mode: status, new care alerts, time-series acoustic measurements, patient-reported concerns, and a right-side research-context panel.
Demo journey (90 seconds)
1. Father starts a voice check-in and speaks freely (plus a consistent reference phrase/task).
2. Audio backend compares selected measurable features with reference recordings. It only measures acoustic differences.
3. AI companion asks one or two approved follow-up questions, based on measured features and the father's own words.
4. With prior consent, an in-app care alert is generated automatically when predefined nonclinical review criteria are met or the father explicitly requests help.
5. Son's dashboard refreshes automatically and shows what changed, what the father reported, and links to related research. A family member may choose to call.
6. If someone describes potential immediate danger (e.g., sudden speech difficulty or severe breathing trouble), the app immediately displays emergency guidance; it does not diagnose or dispatch 911.
Current prototype vs future roadmap
Prototype: deliver tonight	Future development; NOT implemented
Real microphone recording and reference comparison (Person 2)	Clinically validated disease prediction
Two adaptive follow-up question paths (Person 3)	Calibrated personalized disease probabilities
In-app alerts using fictional profiles (Person 3)	SMS/push to real families, caregiver identity verification
Clean senior/family interface (Person 1)	Regulated medical monitoring and emergency dispatch
Curated source links explaining voice-feature research (Person 3)	Clinical study, multi-site validation, privacy/security certification


Critical: A research model's classification accuracy (for example, 84%) is not a new user's probability of disease. Do not invent “COPD 78% / Parkinson's 15%” charts. The family panel shows research associations, not a medical diagnosis or risk percentage. Hypoxemia cannot be ruled in or out by voice; SpO₂ must come from an independent measurement and also has limitations.
Three-person responsibilities — own your files
Developer	Area	Owned files	Deliverable
Person 1: Frontend & UX	Senior mode, family mode, microphone UI, auto-refresh, charts	frontend/**	Father check-in and son's alert view; responsive, accessible and polished
Person 2: Voice Analysis & Backend	Receive and decode audio, create baseline features, compare samples, user/check-in storage, app entry point	backend/main.py, backend/audio_analysis.py, backend/storage.py	POST /api/baseline and POST /api/checkin work with genuine audio
Person 3: AI Conversation, Medical Evidence & Alert Logic	Follow-up question selection, Gemini-assisted wording, reviewed research index, nonclinical alert creation	backend/ai/**, data/research.json, docs/API_CONTRACT.md	Adaptive Q&A plus evidence-linked summary and an alert visible to family


Integration ownership: Person 2 connects the Person 3 router in backend/main.py; Person 1 consumes the agreed APIs. No one edits another person's files until the group confirms the change.
Recommended project structure
VoiceGuard/
├── README.md                     # This file — team-facing setup
├── frontend/                     # Person 1: React or standalone HTML demo
├── backend/
│   ├── __init__.py
│   ├── main.py                   # Person 2: existing FastAPI app
│   ├── audio_analysis.py         # Person 2: real acoustic measurements
│   ├── ai_demo_app.py            # Standalone integration test app
│   └── ai/                       # Person 3: avoid editing teammates' code
│       ├── __init__.py
│       ├── models.py             # Shared Pydantic request/response models
│       ├── conversation.py       # Safe approved question selection + optional Gemini wording
│       ├── evidence.py           # Research-source lookup
│       ├── alerts.py             # Simulated in-app family notifications
│       └── routes.py             # Person 3 FastAPI endpoints
├── data/
│   └── research.json             # Curated papers with limitations
├── docs/
│   └── API_CONTRACT.md           # Freeze this contract together
├── demo/
│   └── scenarios.json            # All fictional demonstration cases
├── tests/
│   └── test_ai_workflow.py
├── requirements-ai.txt
└── .env.example
The structure is a proposed team agreement. It does not mean that all components have already been completed by your teammates.

Quick start — run Person 3's independent API
Python 3.10+:
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-ai.txt
uvicorn backend.ai_demo_app:app --reload
Open http://127.0.0.1:8000/docs and try:
- POST /api/ai/next-question
- POST /api/ai/finalize
- GET /api/alerts
- GET /api/ai/evidence
Real audio belongs to Person 2. The provided AI routes receive a structured voice_changes object (e.g., {"pause_rate": "increased"}) after Person 2 has measured it.

To enable optional Gemini wording only:
pip install google-genai
# Set GEMINI_API_KEY and GEMINI_MODEL in your local environment.
# Never commit keys; explicitly set allow_external_ai=true only with informed consent.
Without Gemini, deterministic question selection works offline. The app may use an LLM to phrase a pre-approved question or summarize reported words, but never to invent a diagnosis or determine urgency.
Integration API handshake
See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md). Core contract:
- POST /api/baseline — Person 2, multipart WAV.
- POST /api/checkin — Person 2, multipart WAV -> returns a checkin_id and measured voice_changes.
- POST /api/ai/next-question — Person 3, JSON with checkin_id, voice_changes, self_report.
- POST /api/ai/finalize — Person 3, JSON with answers and alerts_enabled.
- GET /api/alerts — Person 3, in-memory demo only alerts; frontend polls every ~5 seconds.
Branches and Git workflow
- feature/frontend — Person 1.
- feature/audio-backend — Person 2.
- feature/ai-medical-evidence — Person 3.
- Only merge reviewed, working changes to main. Do not force-push main.
- Commit often; at 7:30 PM connect real endpoints, by 9:00 PM complete the flow, by 10:00 PM freeze new features.
- Each PR should state what worked, what was simulated, and what has NOT been tested.