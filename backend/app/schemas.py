from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CorrectRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Transcript of what the learner said")
    user_id: str = Field(default="abhi")
    mode: str = Field(default="daily")
    duration_seconds: float = Field(default=0, ge=0)


class MistakeItem(BaseModel):
    incorrect_phrase: str
    corrected_phrase: str
    error_type: str = "other"
    explanation: str = ""


class CorrectResponse(BaseModel):
    reply: str = ""
    corrected: str
    mistakes: List[MistakeItem]
    feedback: str = ""
    mode: str = "daily"
    repeat_prompt: str = ""


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to speak")
    voice: str = Field(default="")


class TranscribeResponse(BaseModel):
    text: str


class MistakeOut(BaseModel):
    id: str
    user_id: str
    incorrect_phrase: str
    corrected_phrase: str
    error_type: str
    timestamp: datetime

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    error_type: str
    count: int


class MistakesResponse(BaseModel):
    mistakes: List[MistakeOut]
    stats: List[StatsOut]


class ModeCount(BaseModel):
    mode: str
    count: int


class PracticeLogOut(BaseModel):
    id: str
    user_id: str
    mode: str
    transcript: str
    corrected: str
    reply: str
    mistake_count: int
    duration_seconds: float
    timestamp: datetime

    class Config:
        from_attributes = True


class ProgressResponse(BaseModel):
    total_turns: int
    total_mistakes: int
    speaking_minutes: float
    current_streak_days: int
    last_practice_at: Optional[datetime] = None
    mode_counts: List[ModeCount]
    recent_logs: List[PracticeLogOut]


class RepeatResponse(BaseModel):
    transcript: str
    score: float
    feedback: str


class ConversationTurnOut(BaseModel):
    id: str
    user_id: str
    mode: str
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    turns: List[ConversationTurnOut]
