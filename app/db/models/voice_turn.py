import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class VoiceTurn(Base):
    __tablename__ = "voice_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    stt_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_first_token_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tts_first_audio_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    exceeded_budget: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warning_stage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
