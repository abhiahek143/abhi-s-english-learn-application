import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .database import Base


def _uuid():
    return str(uuid.uuid4())


class Mistake(Base):
    """The mistakes_tracker table.

    Columns: user_id, incorrect_phrase, corrected_phrase, error_type, timestamp.
    Powers the personalized 'weak points' dashboard.
    """

    __tablename__ = "mistakes_tracker"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, index=True, nullable=False, default="abhi")
    incorrect_phrase = Column(String, nullable=False)
    corrected_phrase = Column(String, nullable=False)
    error_type = Column(String, nullable=False, default="other")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConversationTurn(Base):
    """Recent conversation memory used to keep replies on the same topic."""

    __tablename__ = "conversation_turns"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, index=True, nullable=False, default="abhi")
    mode = Column(String, nullable=False, default="daily")
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PracticeLog(Base):
    """One spoken turn for progress stats and streak tracking."""

    __tablename__ = "practice_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, index=True, nullable=False, default="abhi")
    mode = Column(String, nullable=False, default="daily")
    transcript = Column(Text, nullable=False)
    corrected = Column(Text, nullable=False)
    reply = Column(Text, nullable=False)
    mistake_count = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=False, default=0)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
