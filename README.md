# Agentic Loan Voice Agent

End-to-end multilingual loan recovery calling system with:

- Outbound calls via LiveKit SIP trunk
- Realtime voice pipeline (Deepgram STT + Groq LLM + ElevenLabs TTS)
- Dashboard with loan list + one-click call trigger
- SQLite persistence for customers, loans, and call logs

## Features

- Receptionist-style conversation flow
- Dynamic language adaptation (English, Hindi, Telugu, Tamil)
- One question at a time behavior
- Call history and provider error visibility in dashboard

## Project Structure

- `src/loan_agent/api_server.py` - FastAPI backend and API routes
- `src/loan_agent/worker.py` - LiveKit voice worker
- `src/loan_agent/db.py` - SQLite schema + seed data
- `src/loan_agent/prompts.py` - conversation instructions
- `src/loan_agent/language_lock.py` - language detection/switch logic
- `web/index.html` - dashboard UI

## Prerequisites

- Python 3.12+ (3.13 recommended)
- LiveKit Cloud project + outbound SIP trunk
- API keys for Deepgram, Groq, ElevenLabs

## 1) Setup

```bash
cd /Users/appalaraju/Desktop/Agentic_Loan_Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in project root:

```env
LIVEKIT_URL=wss://<your-livekit>.livekit.cloud
LIVEKIT_API_KEY=<livekit_api_key>
LIVEKIT_API_SECRET=<livekit_api_secret>
LIVEKIT_SIP_OUTBOUND_TRUNK_ID=<sip_trunk_id>

DEEPGRAM_API_KEY=<deepgram_key>

GROQ_API_KEY=<groq_key>
GROQ_MODEL=llama-3.1-8b-instant

ELEVENLABS_API_KEY=<elevenlabs_key>
ELEVENLABS_VOICE_ID=<voice_id>
ELEVENLABS_MODEL_ID=eleven_turbo_v2_5
```

## 2) Run

Open two terminals (both inside project root and with `.venv` activated).

Terminal A (API + dashboard):

```bash
PYTHONPATH=src uvicorn loan_agent.api_server:app --host 0.0.0.0 --port 8000
```

Terminal B (voice worker):

```bash
PYTHONPATH=src python -m loan_agent.worker dev
```

Open dashboard:

- http://localhost:8000/

## 3) Test Call

Call a seeded loan (example: loan id 1):

```bash
curl -X POST http://localhost:8000/api/loans/1/call
```

Useful APIs:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/dashboard/loans
curl http://localhost:8000/api/calls
```

## 4) Expected Behavior

- Agent greets first
- Agent asks one question at a time
- Agent responds in one language per turn (no mixed-language sentence)
- Agent switches language only when customer switches

## 5) Stop Services

```bash
pkill -f "uvicorn loan_agent.api_server"
pkill -f "python -m loan_agent.worker"
```

## 6) Push to Git (for sharing with your sir)

If this folder is not a git repo yet:

```bash
git init
git add .
git commit -m "Initial commit: Agentic Loan Voice Agent"
```

Connect remote and push:

```bash
git branch -M main
git remote add origin <your_github_repo_url>
git push -u origin main
```

Example remote URL formats:

- `https://github.com/<username>/<repo>.git`
- `git@github.com:<username>/<repo>.git`
