import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import Base, engine, get_db
from .llm import (
    CorrectionError,
    SpeechError,
    TranscriptionError,
    get_conversation_reply,
    get_correction,
    get_speech_audio,
    get_transcription,
    compare_texts,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Abhi's Self Learn API", version="1.0.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/correct", response_model=schemas.CorrectResponse)
def correct_sentence(payload: schemas.CorrectRequest, db: Session = Depends(get_db)):
    """Takes one spoken sentence, returns the corrected version + flagged mistakes,
    and logs any mistakes into the mistakes_tracker table for the dashboard."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    mode = payload.mode.strip() or "daily"
    try:
        history = crud.get_recent_conversation_turns(db, payload.user_id, mode, limit=50)
        result = get_correction(payload.text, mode, history)
        reply = get_conversation_reply(payload.text, mode, history)
    except CorrectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    mistake_items = [schemas.MistakeItem(**m) for m in result.get("mistakes", [])]
    if mistake_items:
        crud.add_mistakes(db, payload.user_id, mistake_items)
    crud.add_conversation_turns(db, payload.user_id, mode, payload.text, reply)
    crud.add_practice_log(
        db=db,
        user_id=payload.user_id,
        mode=mode,
        transcript=payload.text,
        corrected=result["corrected"],
        reply=reply,
        mistake_count=len(mistake_items),
        duration_seconds=payload.duration_seconds,
    )

    return schemas.CorrectResponse(
        reply=reply,
        corrected=result["corrected"],
        mistakes=mistake_items,
        feedback=result.get("feedback", ""),
        mode=mode,
        repeat_prompt=result["corrected"],
    )


@app.post("/api/transcribe", response_model=schemas.TranscribeResponse)
async def transcribe_audio(request: Request):
    """Transcribes browser-recorded mic audio with Groq Whisper."""
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="audio must not be empty")
    if len(audio) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="audio is too large")

    try:
        text = get_transcription(audio, request.headers.get("content-type", "audio/webm"))
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return schemas.TranscribeResponse(text=text)


@app.post("/api/speech")
def speech(payload: schemas.SpeechRequest):
    """Generates human-like Groq Orpheus speech audio for coach replies."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    try:
        audio = get_speech_audio(payload.text, payload.voice)
    except SpeechError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/mistakes", response_model=schemas.MistakesResponse)
def list_mistakes(user_id: str = Query(default="abhi"), db: Session = Depends(get_db)):
    rows = crud.get_mistakes(db, user_id)
    stats = crud.get_stats(db, user_id)
    return schemas.MistakesResponse(mistakes=rows, stats=stats)


@app.get("/api/progress", response_model=schemas.ProgressResponse)
def progress(user_id: str = Query(default="abhi"), db: Session = Depends(get_db)):
    return schemas.ProgressResponse(**crud.get_progress(db, user_id))


@app.get("/api/conversation", response_model=schemas.ConversationResponse)
def get_conversation(
    user_id: str = Query(default="abhi"),
    mode: str = Query(default="daily"),
    db: Session = Depends(get_db),
):
    turns = crud.get_recent_conversation_turns(db, user_id=user_id, mode=mode, limit=50)
    return schemas.ConversationResponse(turns=turns)


@app.delete("/api/conversation")
def clear_conversation(user_id: str = Query(default="abhi"), mode: str = Query(default=""), db: Session = Depends(get_db)):
    deleted = crud.clear_conversation(db, user_id, mode)
    return {"deleted": deleted}


@app.delete("/api/mistakes")
def clear_mistakes(user_id: str = Query(default="abhi"), db: Session = Depends(get_db)):
    deleted = crud.clear_mistakes(db, user_id)
    return {"deleted": deleted}


@app.post("/api/repeat", response_model=schemas.RepeatResponse)
async def repeat_evaluate(request: Request):
    """Accepts a small audio clip (form file 'file') and an 'expected' text field, returns transcript + score."""
    form = await request.form()
    expected = (form.get("expected") or "").strip()
    if not expected:
        raise HTTPException(status_code=400, detail="expected text is required")

    upload = form.get("file")
    if upload is None:
        # also accept raw body as audio
        audio = await request.body()
        content_type = request.headers.get("content-type", "audio/webm")
    else:
        try:
            audio = await upload.read()
            content_type = getattr(upload, "content_type", "audio/webm") or "audio/webm"
        except Exception as e:
            raise HTTPException(status_code=400, detail="could not read uploaded file") from e

    if not audio:
        raise HTTPException(status_code=400, detail="audio must not be empty")

    try:
        transcript = get_transcription(audio, content_type)
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    result = compare_texts(expected, transcript)
    return schemas.RepeatResponse(transcript=result["transcript"], score=result["score"], feedback=result["feedback"])


@app.get("/api/tts-status")
def tts_status():
    """Quick check whether Groq Orpheus TTS is available for this API key.

    Attempts a tiny TTS request and reports availability. Caller should handle
    false responses by showing guidance to accept model terms in the Groq Console.
    """
    try:
        # attempt a minimal TTS call; this will raise SpeechError if terms not accepted
        get_speech_audio("Hello", voice="")
        return {"available": True}
    except SpeechError as e:
        return {"available": False, "detail": str(e)}
