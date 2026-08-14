from collections import Counter
from datetime import date, timedelta
from typing import List

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import models, schemas


def add_mistakes(db: Session, user_id: str, items: List[schemas.MistakeItem]) -> List[models.Mistake]:
    rows = []
    for item in items:
        row = models.Mistake(
            user_id=user_id,
            incorrect_phrase=item.incorrect_phrase,
            corrected_phrase=item.corrected_phrase,
            error_type=item.error_type or "other",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def add_conversation_turns(db: Session, user_id: str, mode: str, user_text: str, reply: str) -> None:
    db.add_all(
        [
            models.ConversationTurn(user_id=user_id, mode=mode, role="user", content=user_text),
            models.ConversationTurn(user_id=user_id, mode=mode, role="assistant", content=reply),
        ]
    )
    db.commit()


def get_recent_conversation_turns(
    db: Session,
    user_id: str,
    mode: str,
    limit: int = 8,
) -> List[models.ConversationTurn]:
    rows = (
        db.query(models.ConversationTurn)
        .filter(models.ConversationTurn.user_id == user_id, models.ConversationTurn.mode == mode)
        .order_by(models.ConversationTurn.timestamp.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def clear_conversation(db: Session, user_id: str, mode: str = "") -> int:
    query = delete(models.ConversationTurn).where(models.ConversationTurn.user_id == user_id)
    if mode:
        query = query.where(models.ConversationTurn.mode == mode)
    result = db.execute(query)
    db.commit()
    return result.rowcount or 0


def add_practice_log(
    db: Session,
    user_id: str,
    mode: str,
    transcript: str,
    corrected: str,
    reply: str,
    mistake_count: int,
    duration_seconds: float,
) -> models.PracticeLog:
    row = models.PracticeLog(
        user_id=user_id,
        mode=mode,
        transcript=transcript,
        corrected=corrected,
        reply=reply,
        mistake_count=mistake_count,
        duration_seconds=duration_seconds,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_mistakes(db: Session, user_id: str) -> List[models.Mistake]:
    return (
        db.query(models.Mistake)
        .filter(models.Mistake.user_id == user_id)
        .order_by(models.Mistake.timestamp.desc())
        .all()
    )


def get_stats(db: Session, user_id: str):
    rows = get_mistakes(db, user_id)
    counts = Counter(r.error_type for r in rows)
    return [{"error_type": k, "count": v} for k, v in counts.items()]


def get_recent_practice_logs(db: Session, user_id: str, limit: int = 8) -> List[models.PracticeLog]:
    return (
        db.query(models.PracticeLog)
        .filter(models.PracticeLog.user_id == user_id)
        .order_by(models.PracticeLog.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_progress(db: Session, user_id: str):
    rows = (
        db.query(models.PracticeLog)
        .filter(models.PracticeLog.user_id == user_id)
        .order_by(models.PracticeLog.timestamp.desc())
        .all()
    )
    mode_counts = Counter(row.mode for row in rows)
    practice_dates = {row.timestamp.date() for row in rows if row.timestamp}
    current_streak = _current_streak(practice_dates)
    speaking_seconds = sum(row.duration_seconds or 0 for row in rows)
    total_mistakes = sum(row.mistake_count or 0 for row in rows)

    return {
        "total_turns": len(rows),
        "total_mistakes": total_mistakes,
        "speaking_minutes": round(speaking_seconds / 60, 1),
        "current_streak_days": current_streak,
        "last_practice_at": rows[0].timestamp if rows else None,
        "mode_counts": [{"mode": mode, "count": count} for mode, count in mode_counts.items()],
        "recent_logs": rows[:8],
    }


def _current_streak(practice_dates: set[date]) -> int:
    if not practice_dates:
        return 0

    today = date.today()
    cursor = today if today in practice_dates else today - timedelta(days=1)
    streak = 0
    while cursor in practice_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def clear_mistakes(db: Session, user_id: str) -> int:
    result = db.execute(
        delete(models.Mistake).where(models.Mistake.user_id == user_id)
    )
    db.commit()
    return result.rowcount or 0
