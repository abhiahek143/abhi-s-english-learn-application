# Abhi's English Learn — AI Conversation Coach

> A context-aware, voice-first AI English coaching app that behaves like a real person having a natural English conversation with you.

![App Screenshot](image.png)

---

## What it does

Speak in English (or try to!) and the app acts as your personal English coach + conversation partner:

1. **Listens** to your voice via the microphone
2. **Transcribes** your speech using Groq Whisper (highly accurate STT)
3. **Corrects** your sentence — grammar, tense, vocabulary, and real-world phrasing (flags common Indian-English mistakes like "having a doubt", "today morning", "do the needful")
4. **Replies** like a real person based on the active practice mode (friend, interviewer, coworker, etc.)
5. **Remembers** the entire conversation (up to 50 turns) so replies are always context-aware
6. **Speaks back** using Groq Orpheus (human-like voice) with browser TTS as fallback

---

## Features

### 5 Practice Modes

| Mode | Persona | What you practice |
|---|---|---|
| **Daily Conversation** | Friendly chat partner | Casual chats, plans, hobbies, daily life |
| **Interview Practice** | Mock hiring manager | STAR answers, executive presence, recruiter-ready English |
| **Office English** | Workplace colleague | Standups, status updates, polite requests, business idioms |
| **Travel English** | Airport / hotel agent | Check-in, ordering food, directions, real travel scenarios |
| **Storytelling** | Co-story creator | Vivid narrative, plot building, descriptive English |

Each mode has a dedicated AI persona, system prompt, and coaching focus so corrections are always contextually appropriate.

---

### Context-Aware Conversation Memory

- Full conversation history (up to 50 turns) is stored per user per mode in SQLite
- Every AI correction and reply references what was said earlier in the conversation
- Switching modes loads that mode's own separate conversation history
- "Clear conversation" resets only the active mode's history

---

### Real-World English Coaching

The correction engine goes beyond grammar — it coaches for natural, native-like phrasing:

| Error type | Example |
|---|---|
| Grammar | "I am having" → "I have" |
| Tense | "I was going yesterday morning" → "I went yesterday morning" |
| Indianism | "today morning" → "this morning" |
| Indianism | "having a doubt" → "have a question" |
| Workplace | "do the needful" → "take care of this" |
| Interview | "I passed out in 2024" → "I graduated in 2024" |
| Travel | "Give water" → "Could I please have a glass of water?" |
| Naturalness | Flags overly formal or unnatural phrasing |
| Tone | Coaches politeness and formality level |

Each mistake gets: flagged phrase, corrected phrase, error type badge, one-line coaching note, and an encouraging feedback message.

---

### Repeat-After-Me

- Tap the Repeat button on any corrected sentence
- App speaks the corrected sentence aloud
- You record yourself repeating it
- App transcribes your attempt and gives a similarity score + feedback

---

### Mistakes Dashboard

- Bar chart of all mistake types (Grammar, Tense, Vocabulary, Naturalness, Idiom, Tone)
- Full table of every flagged mistake with: what you said, correct version, type, and timestamp
- One-click "Clear history" to reset

---

### Human Voice (Groq Orpheus TTS)

- Uses `canopylabs/orpheus-v1-english` model (voice: hannah) for natural human-like replies
- Automatically falls back to browser SpeechSynthesis if Orpheus terms are not accepted
- "Enable human voice" button opens Groq Console to accept model terms

---

## Tech Stack

```
Frontend    React + Vite, MediaRecorder API, Lucide icons
Backend     FastAPI (Python), Uvicorn
Database    SQLAlchemy + SQLite (file-based, no setup needed)
AI Models   Groq API:
              - qwen/qwen3.6-27b          (correction + conversation)
              - whisper-large-v3-turbo    (speech-to-text)
              - canopylabs/orpheus-v1-english  (text-to-speech)
Deployment  Docker + docker-compose
```

---

## Project Structure

```
abhis-self-learn/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI routes + request handling
│   │   ├── llm.py         # Groq API calls, personas, correction engine
│   │   ├── crud.py        # Database read/write helpers
│   │   ├── models.py      # SQLAlchemy table definitions
│   │   ├── schemas.py     # Pydantic request/response schemas
│   │   └── database.py    # DB engine + session setup
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env               # Your local secrets (NOT committed)
│   └── .env.example       # Template — copy this to .env
├── frontend/
│   ├── src/
│   │   └── App.jsx        # Full UI: chat, mic, modes, dashboard
│   ├── index.html
│   ├── vite.config.js
│   └── Dockerfile
└── docker-compose.yml
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/correct` | Transcript → correction, mistakes, AI reply |
| `POST` | `/api/transcribe` | Raw audio → transcribed text (Groq Whisper) |
| `POST` | `/api/speech` | Text → WAV audio (Groq Orpheus) |
| `POST` | `/api/repeat` | Audio + expected text → similarity score + feedback |
| `GET` | `/api/conversation` | Fetch conversation history for a mode |
| `DELETE` | `/api/conversation` | Clear conversation for a mode |
| `GET` | `/api/mistakes` | All logged mistakes + error type stats |
| `DELETE` | `/api/mistakes` | Clear all logged mistakes |
| `GET` | `/api/progress` | Practice stats: streaks, speaking time, mode counts |
| `GET` | `/api/tts-status` | Check if Orpheus TTS is available |
| `GET` | `/api/health` | Health check |

### POST /api/correct — Request

```json
{
  "text": "I am having a doubt about this.",
  "user_id": "abhi",
  "mode": "daily",
  "duration_seconds": 4.2
}
```

### POST /api/correct — Response

```json
{
  "reply": "That's a great question! What exactly are you unsure about?",
  "corrected": "I have a question about this.",
  "mistakes": [
    {
      "incorrect_phrase": "having a doubt",
      "corrected_phrase": "have a question",
      "error_type": "idiom",
      "explanation": "Native speakers say 'have a question', not 'having a doubt'."
    }
  ],
  "feedback": "Nice effort — your sentence was clear and confident!",
  "mode": "daily",
  "repeat_prompt": "I have a question about this."
}
```

---

## Quickstart

### Option 1 — Docker (recommended)

```bash
git clone https://github.com/abhiahek143/abhi-s-english-learn-application.git
cd abhi-s-english-learn-application

cp backend/.env.example backend/.env
# Add your GROQ_API_KEY to backend/.env
# Get a free key at https://console.groq.com/keys

docker compose up --build
```

Open **http://localhost:8080** in your browser.

---

### Option 2 — Local Development

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY to backend/.env
uvicorn app.main:app --reload --port 8000
```

**Frontend** (new terminal):
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Get from https://console.groq.com/keys |
| `GROQ_CORRECTION_MODEL` | `qwen/qwen3.6-27b` | Model for correction |
| `GROQ_CONVERSATION_MODEL` | `qwen/qwen3.6-27b` | Model for conversational replies |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` | Speech-to-text model |
| `GROQ_TTS_MODEL` | `canopylabs/orpheus-v1-english` | Text-to-speech model |
| `GROQ_TTS_VOICE` | `hannah` | Orpheus voice name |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins |

**Never commit `backend/.env`** — it is in `.gitignore` by default.

---

## Database Schema

| Table | Purpose |
|---|---|
| `conversation_turns` | All chat turns (user + assistant) per user per mode |
| `mistakes_tracker` | Every flagged mistake with type and timestamp |
| `practice_logs` | Each practice session with duration, mode, mistake count |

SQLite file is at `backend/abhis_self_learn.db` — no database server needed.

---

## Security Notes

- `backend/.env` is in `.gitignore` and will never be committed
- Use GitHub Secrets or environment variables for production
- If you accidentally committed `.env`, remove from history:

```bash
git filter-repo --path backend/.env --invert-paths
git push --force
```

---

## Built by

**Abhishek** — learning in public

> This project demonstrates end-to-end AI integration: voice → STT → LLM correction + conversation → TTS, with a real database-backed memory system and 5 domain-specific coaching personas.
