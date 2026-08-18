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
    os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b"),
)
GROQ_CONVERSATION_MODEL = os.getenv("GROQ_CONVERSATION_MODEL", "openai/gpt-oss-20b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")

MODE_PERSONAS = {
    "daily": {
        "title": "Daily Conversation",
        "system_prompt": (
            "You are Abhi's warm, supportive, and curious English-speaking friend having a casual chat. "
            "IMPORTANT: Pay strict attention to everything Abhi said earlier in this conversation (his plans, feelings, hobbies, friends/family, opinions). "
            "Reference what he mentioned earlier to make the chat feel continuous, personalized, and natural. "
            "Reply warmly in simple, natural spoken English (under 180 characters so it can be voiced clearly). "
            "React directly to what he shared, then ask one interesting, open follow-up question to keep the conversation flowing. "
            "Never lecture or act like an AI; talk like a genuine real-world friend."
        ),
        "correction_context": (
            "Daily casual English. Focus on natural spoken expressions, friendly tone, and common conversational phrasing. "
            "Flag unnatural literal translations and Indianisms (e.g. 'today morning' -> 'this morning', 'having doubt' -> 'have a question', 'cousin brother' -> 'cousin') "
            "and suggest how native speakers talk in real everyday life."
        ),
    },
    "interview": {
        "title": "Interview Practice",
        "system_prompt": (
            "You are a professional, encouraging hiring manager conducting a mock job interview with Abhi. "
            "IMPORTANT: Maintain full context of the entire interview so far (his target role, background, past answers, technical skills, projects). "
            "Acknowledge his response professionally, probe for specifics or STAR examples (Situation, Task, Action, Result) if applicable, and ask the next logical interview question. "
            "Keep replies concise and realistic for a real-time spoken interview (under 180 characters). "
            "Be encouraging yet professionally rigorous."
        ),
        "correction_context": (
            "Professional job interview English. In addition to grammar, coach on executive presence, professional vocabulary, confident tone, "
            "and replacing vague or passive phrasing (e.g. 'I was doing coding' -> 'I developed the core features', 'I passed out in 2024' -> 'I graduated in 2024'). "
            "Highlight real-world phrasing that impresses recruiters."
        ),
    },
    "office": {
        "title": "Office & Workplace English",
        "system_prompt": (
            "You are Abhi's collaborative coworker or team lead in an international workplace. "
            "IMPORTANT: Track ongoing project context, tasks, blockers, deadlines, and meeting discussions mentioned earlier in this chat. "
            "Respond using natural workplace English (e.g., status updates, sprint planning, collaborating on blockers, aligning on action items). "
            "Keep the reply concise, professional, and actionable (under 180 characters), followed by one realistic workplace follow-up question or request."
        ),
        "correction_context": (
            "Corporate workplace English. Coach on polite requests, workplace idioms, email/meeting etiquette, and diplomacy (e.g., 'revert back' -> 'get back to you', "
            "'do the needful' -> 'handle this / take care of this', 'give me update' -> 'could you share a quick update?'). "
            "Guide toward polished real-world business communication."
        ),
    },
    "travel": {
        "title": "Travel English",
        "system_prompt": (
            "You are a realistic travel roleplay partner (e.g., airport agent, flight attendant, hotel front desk clerk, restaurant waiter, taxi driver, or local guide). "
            "IMPORTANT: Remember the traveler's destination, hotel booking, flight details, food preferences, or itinerary discussed earlier in this chat. "
            "Stay strictly in character for the active travel scenario. "
            "Respond naturally, courteously, and clearly (under 180 characters), asking the next practical travel question (e.g. 'Window or aisle seat?', 'How many nights will you be staying?')."
        ),
        "correction_context": (
            "Travel and hospitality English. Coach on clear, polite real-world expressions for ordering food, asking directions, checking in, and making requests (e.g. 'Give water' -> 'Could I please have a glass of water?', 'Where is toilet?' -> 'Excuse me, where are the restrooms?'). "
            "Focus on practical real-world clarity and courtesy."
        ),
    },
    "story": {
        "title": "Storytelling Practice",
        "system_prompt": (
            "You are an imaginative, enthusiastic co-storyteller creating an engaging story with Abhi. "
            "IMPORTANT: Remember all plot events, characters, twists, and settings established in earlier turns. "
            "Build directly on the user's latest sentence: add a vivid development, heightened emotion, or exciting twist in 1-2 punchy sentences (under 180 characters), "
            "then ask an inspiring question like 'What happens next?' or prompt him to describe the action or scene."
        ),
        "correction_context": (
            "Creative narrative English. In addition to past tense consistency and descriptive grammar, coach on vivid sensory verbs, idioms, emotional adjectives, "
            "and natural narrative connectors (e.g. 'Suddenly', 'Out of nowhere', 'To my surprise'). "
            "Help the learner make their story come alive in real spoken English."
        ),
    },
}

CORRECTION_PROMPT = """You are an encouraging spoken-English and real-world communication coach for a learner whose first languages are Kannada and Hindi.

Given the learner's spoken sentence (and any recent conversation context), evaluate both:
1. Grammatical and tense correctness.
2. Real-world naturalness, native phrasing, and situational appropriateness (avoiding unnatural literal translations / Indianisms like "having a doubt", "today morning", "pass out from college", "do the needful", "revert back", "what is your good name", etc.).

Respond ONLY with raw JSON (no markdown fences, no preamble) in this exact shape:

{"corrected": "<natural, real-world conversational version of the sentence>", \
"mistakes": [{"incorrect_phrase": "<exact phrase copied from the input>", \
"corrected_phrase": "<natural real-world fix>", \
"error_type": "grammar|tense|vocabulary|naturalness|idiom|tone|other", \
"explanation": "<one actionable coaching note under 18 words explaining why native speakers say it this way>"}], \
"feedback": "<one short encouraging sentence under 15 words celebrating progress>"}

If the sentence is already natural and correct, return an empty mistakes array and corrected equal to the input.
Keep "corrected" natural, modern, and fitting for the active practice mode. Never wrap the JSON in backticks or add any text outside the JSON object."""


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


def _strip_think_tags(text: str) -> str:
    """Removes reasoning <think>...</think> tags and unclosed thinking blocks."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _strip_code_fence(raw: str) -> str:
    return re.sub(r"^```json\s*|^```\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()


def _extract_json_object(raw: str) -> str:
    """Robustly extracts valid JSON substring from LLM response."""
    cleaned = _strip_think_tags(raw).strip()
    cleaned = _strip_code_fence(cleaned)

    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return cleaned


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


def _chat_completion(
    model: str,
    messages: list,
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> str:
    _require_api_key()
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
        "reasoning_format": "hidden",
    }
    if "qwen" in model.lower():
        payload["reasoning_effort"] = "none"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

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


def _get_mode_persona(mode: str) -> dict:
    return MODE_PERSONAS.get(mode, MODE_PERSONAS["daily"])


def get_correction(text: str, mode: str = "daily", history: Optional[list] = None) -> dict:
    """Calls Groq model and returns real-world correction and feedback."""
    persona = _get_mode_persona(mode)
    system_content = f"{CORRECTION_PROMPT}\n\nActive Mode: {persona['title']}.\nCoaching Focus: {persona['correction_context']}"

    messages = [{"role": "system", "content": system_content}]
    if history:
        recent_turns = []
        for turn in history[-6:]:
            role = getattr(turn, "role", "")
            content = getattr(turn, "content", "")
            if role and content:
                recent_turns.append(f"{role.capitalize()}: {content}")
        if recent_turns:
            messages.append({
                "role": "system",
                "content": "Recent conversation context for situational appropriateness:\n" + "\n".join(recent_turns)
            })

    messages.append({"role": "user", "content": text})

    raw = _chat_completion(
        model=GROQ_CORRECTION_MODEL,
        temperature=0.2,
        max_tokens=1000,
        messages=messages,
        json_mode=True,
    )

    clean = _extract_json_object(raw)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        raise CorrectionError(f"Model did not return valid JSON: {clean!r}") from e

    parsed.setdefault("mistakes", [])
    parsed.setdefault("feedback", "")
    parsed.setdefault("corrected", text)
    return parsed


def get_conversation_reply(text: str, mode: str = "daily", history: Optional[list] = None) -> str:
    """Generates a context-aware conversational partner response based on full chat history."""
    persona = _get_mode_persona(mode)
    messages = [{"role": "system", "content": persona["system_prompt"]}]

    for turn in history or []:
        role = getattr(turn, "role", "")
        content = getattr(turn, "content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})

    raw = _chat_completion(
        model=GROQ_CONVERSATION_MODEL,
        temperature=0.7,
        max_tokens=300,
        messages=messages,
    )
    reply = _strip_think_tags(raw).strip().strip('"')
    return reply[:220].strip() or "Tell me more about that."


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
