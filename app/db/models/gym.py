import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

def now_utc():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

class Workout(Base):
    __tablename__ = "workouts"

    id = Column(String, primary_key=True, default=generate_uuid)
    date = Column(DateTime(timezone=True), default=now_utc)
    split_name = Column(String, nullable=True)  # e.g., Push, Pull, Legs, Upper, Lower
    duration_min = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    energy_rating = Column(Integer, nullable=True)  # 1 to 5 scale

    sets = relationship("ExerciseSet", back_populates="workout", cascade="all, delete-orphan", order_by="ExerciseSet.set_number")

class ExerciseSet(Base):
    __tablename__ = "exercise_sets"

    id = Column(String, primary_key=True, default=generate_uuid)
    workout_id = Column(String, ForeignKey("workouts.id"), nullable=False)
    exercise = Column(String, nullable=False)  # Normalized lower name e.g. "bench press"
    set_number = Column(Integer, default=1)
    reps = Column(Integer, nullable=False)
    weight_kg = Column(Float, nullable=False)
    rpe = Column(Float, nullable=True)  # Rate of Perceived Exertion (1-10)

    workout = relationship("Workout", back_populates="sets")

class BodyMetric(Base):
    __tablename__ = "body_metrics"

    id = Column(String, primary_key=True, default=generate_uuid)
    date = Column(DateTime(timezone=True), default=now_utc)
    weight_kg = Column(Float, nullable=False)
    body_fat_pct = Column(Float, nullable=True)
    measurements_json = Column(Text, default="{}")  # waist, chest, arms, etc.

class ExercisePR(Base):
    __tablename__ = "exercise_prs"

    exercise = Column(String, primary_key=True)
    best_weight = Column(Float, nullable=False)
    best_reps = Column(Integer, nullable=False)
    est_1rm = Column(Float, nullable=False)  # Epley formula: w * (1 + r / 30)
    achieved_on = Column(DateTime(timezone=True), default=now_utc)
