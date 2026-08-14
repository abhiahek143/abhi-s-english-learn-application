import json
import os
import re
from typing import Optional

import requests

GROQ_CHAT_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_SPEECH_API_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_TRANSCRIPTION_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_CORRECTION_MODEL = os.getenv(
    "GROQ_CORRECTION_MODEL",
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
GROQ_CONVERSATION_MODEL = os.getenv("GROQ_CONVERSATION_MODEL", "openai/gpt-oss-20b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")

MODE_GUIDANCE = {
    "daily": "daily conversation about ordinary life, plans, family, hobbies, and feelings",
    "interview": "job interview practice with clear, confident professional answers",
    "office": "workplace English for meetings, updates, requests, and collaboration",
    "travel": "travel English for transport, hotels, food, directions, and small talk",
    "story": "storytelling practice with details, sequence, emotions, and natural narration",
}

CORRECTION_PROMPT = """You are an encouraging spoken-English coach for a learner whose first \
languages are Kannada and Hindi. Given one sentence the learner just said aloud, respond \
ONLY with raw JSON (no markdown fences, no preamble) in this exact shape:

{"corrected": "<grammatically correct natural version of the sentence>", \
"mistakes": [{"incorrect_phrase": "<exact wrong phrase copied from the input>", \
"corrected_phrase": "<the fix>", "error_type": "grammar|tense|vocabulary|other", \
"explanation": "<one simple coaching note under 18 words>"}], \
"feedback": "<one short encouraging sentence, under 15 words>"}

If the sentence is already correct, return an empty mistakes array and corrected equal \
to the input. Keep "corrected" natural and conversational, not overly formal. Never \
wrap the JSON in backticks or add any text outside the JSON object."""

CONVERSATION_PROMPT = """You are Abhi's friendly English conversation partner. Reply to \
the meaning of what he said, not the grammar. Use simple, natural spoken English. Keep \
the reply under 180 characters so it can be spoken clearly. Usually answer first, then \
ask one easy follow-up question. Use the conversation history to stay on topic. Output \
plain text only."""


class CorrectionError(Exception):
    pass


class SpeechError(Exception):
    pass


class TranscriptionError(Exception):
    pass


def _request_error_message(error: requests.RequestException) -> str:
    response = getattr(error, "response", None)
    if response is None:
        return str(error)

    try:
        body = response.json()
        message = body.get("error", {}).get("message") or body.get("detail")
        if message:
            return message
    except ValueError:
        pass

    return response.text or str(error)


def _strip_code_fence(raw: str) -> str:
    return re.sub(r"^```json\s*|^```\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()


def _require_api_key(error_cls=CorrectionError) -> None:
    if not GROQ_API_KEY:
        raise error_cls(
            "GROQ_API_KEY is not set. Add your key to backend/.env from "
            "https://console.groq.com/keys"
        )


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}"}


def _json_headers() -> dict:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _chat_completion(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    _require_api_key()
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    try:
        resp = requests.post(GROQ_CHAT_API_URL, headers=_json_headers(), json=payload, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise CorrectionError(f"Groq API request failed: {_request_error_message(e)}") from e

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise CorrectionError(f"Unexpected Groq response shape: {data}") from e


def _mode_guidance(mode: str) -> str:
    return MODE_GUIDANCE.get(mode, MODE_GUIDANCE["daily"])


def get_correction(text: str, mode: str = "daily") -> dict:
    """Calls Llama 3.3 via Groq and returns correction data."""
    raw = _chat_completion(
        model=GROQ_CORRECTION_MODEL,
        temperature=0.3,
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": f"{CORRECTION_PROMPT}\nPractice mode context: {_mode_guidance(mode)}.",
            },
            {"role": "user", "content": text},
        ],
    )

    clean = _strip_code_fence(raw)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        raise CorrectionError(f"Model did not return valid JSON: {clean!r}") from e

    parsed.setdefault("mistakes", [])
    parsed.setdefault("feedback", "")
    parsed.setdefault("corrected", text)
    return parsed


def get_conversation_reply(text: str, mode: str = "daily", history: Optional[list] = None) -> str:
    """Uses a separate Groq model for the conversational partner response."""
    messages = [
        {
            "role": "system",
            "content": f"{CONVERSATION_PROMPT}\nCurrent practice mode: {_mode_guidance(mode)}.",
        }
    ]
    for turn in history or []:
        role = getattr(turn, "role", "")
        content = getattr(turn, "content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})

    raw = _chat_completion(
        model=GROQ_CONVERSATION_MODEL,
        temperature=0.75,
        max_tokens=120,
        messages=messages,
    )
    reply = raw.strip().strip('"')
    return reply[:200].strip() or "Tell me more about that."


def get_transcription(audio: bytes, content_type: str = "audio/webm") -> str:
    """Transcribes browser-recorded audio using Groq Whisper."""
    _require_api_key(TranscriptionError)
    if not audio:
        raise TranscriptionError("audio must not be empty")

    mime_type = (content_type or "audio/webm").split(";", 1)[0].strip() or "audio/webm"
    extension = {
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/webm": "webm",
    }.get(mime_type, "webm")
    files = {"file": (f"speech.{extension}", audio, mime_type)}
    data = {
        "model": GROQ_STT_MODEL,
        "language": "en",
        "response_format": "json",
        "temperature": "0",
        "prompt": "Abhi is practicing spoken English. Transcribe his sentence clearly.",
    }

    try:
        resp = requests.post(
            GROQ_TRANSCRIPTION_API_URL,
            headers=_auth_headers(),
            files=files,
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TranscriptionError(f"Groq transcription failed: {_request_error_message(e)}") from e

    payload = resp.json()
    return (payload.get("text") or "").strip()


def _trim_for_tts(text: str) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= 200:
        return clean
    trimmed = clean[:197].rsplit(" ", 1)[0].rstrip(".,!?;:")
    return f"{trimmed}..."


def get_speech_audio(text: str, voice: str = "") -> bytes:
    """Converts short text into Groq Orpheus WAV audio."""
    _require_api_key(SpeechError)
    speech_text = _trim_for_tts(text)
    if not speech_text:
        raise SpeechError("text must not be empty")

    payload = {
        "model": GROQ_TTS_MODEL,
        "input": speech_text,
        "voice": voice or GROQ_TTS_VOICE,
        "response_format": "wav",
    }
    try:
        resp = requests.post(GROQ_SPEECH_API_URL, headers=_json_headers(), json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SpeechError(f"Groq speech request failed: {_request_error_message(e)}") from e

    return resp.content


def compare_texts(expected: str, actual: str) -> dict:
    """Simple text similarity and short feedback for repeat-after-me."""
    import re
    from difflib import SequenceMatcher

    def norm(s: str) -> str:
        s = (s or '').lower()
        s = re.sub(r"[^a-z0-9 '\\t\\n\\r]+", ' ', s)
        s = re.sub(r"\s+", ' ', s).strip()
        return s

    e = norm(expected)
    a = norm(actual)
    if not a:
        return {"transcript": actual or "", "score": 0.0, "feedback": "I couldn't hear you clearly."}

    ratio = SequenceMatcher(None, e, a).ratio()
    score = round(ratio * 100, 1)
    if ratio >= 0.9:
        fb = "Great — clear and natural."
    elif ratio >= 0.75:
        fb = "Good — work on rhythm and endings."
    else:
        fb = "Try speaking a bit slower and finish the words."

    return {"transcript": actual, "score": score, "feedback": fb}
