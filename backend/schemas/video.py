from datetime import datetime
from typing import Any
from typing import Literal
import os
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QuizConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    easy_count: int = Field(default=12, ge=0, strict=True)
    medium_count: int = Field(default=12, ge=0, strict=True)
    hard_count: int = Field(default=12, ge=0, strict=True)
    question_generation_mode: Literal["default", "custom"] = "default"

    @property
    def total_questions(self):
        return self.easy_count + self.medium_count + self.hard_count

    @model_validator(mode="after")
    def validate_distribution(self):
        maximum = int(os.getenv("MAX_QUIZ_QUESTIONS", "60"))
        if not 1 <= self.total_questions <= maximum:
            raise ValueError(f"Select between 1 and {maximum} questions overall.")
        if self.question_generation_mode == "default" and (self.easy_count, self.medium_count, self.hard_count) != (12, 12, 12):
            raise ValueError("Default Quiz requires 12 Easy, 12 Medium and 12 Hard questions.")
        return self

class YouTubeRequest(BaseModel):
    url: str

class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_type: str
    original_filename: str | None
    stored_filename: str
    source_url: str | None
    status: str
    error_message: str | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime

class TranscriptOut(BaseModel):
    video_id: int
    text: str
    language: str | None
    segments: list[dict[str, Any]]

class ExamSubmission(BaseModel):
    answers: dict[int, str]


class ExamAttemptStartRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    mode: Literal["practice", "exam"] = "exam"
    time_limit_seconds: int | None = Field(default=None, ge=60, le=14400)
    quiz_version: int | None = Field(default=None, ge=1)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank.")
        return value


class ExamAttemptSubmission(BaseModel):
    answers: dict[int, str] = Field(default_factory=dict)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, answers: dict[int, str]) -> dict[int, str]:
        if any(question_id <= 0 for question_id in answers):
            raise ValueError("Question IDs must be positive integers.")
        if any(len(answer) > 500 for answer in answers.values()):
            raise ValueError("Answers must be at most 500 characters.")
        return answers


class ExamStartQuestion(BaseModel):
    id: int
    video_id: int
    question: str
    options: list[str]
    difficulty: str
    timestamp_seconds: int | None


class ExamAttemptStartResponse(BaseModel):
    attempt_id: int
    video_id: int
    quiz_version: int
    status: str
    total_questions: int
    started_at: datetime
    questions: list[ExamStartQuestion]
    notice: str
    mode: str = "exam"
    time_limit_seconds: int | None = None
    expires_at: datetime | None = None


class ExamAttemptResultQuestion(BaseModel):
    question_id: int
    question: str
    options: list[str]
    selected_answer: str | None
    correct_answer: str
    correct: bool
    explanation: str
    feedback: str
    difficulty: str | None = None
    timestamp_seconds: int | None = None
    evidence: str | None = None


class ExamAttemptResultResponse(BaseModel):
    attempt_id: int
    video_id: int
    quiz_version: int
    status: str
    submitted_at: datetime
    score: int
    total: int
    percentage: int
    feedback: str
    results: list[ExamAttemptResultQuestion]
    incorrect: int = 0
    unanswered: int = 0
    time_taken_seconds: int = 0
    difficulty_performance: dict[str, Any] = Field(default_factory=dict)


class ExamAttemptHistoryItem(BaseModel):
    attempt_id: int
    video_id: int
    quiz_version: int
    status: str
    total_questions: int
    score: int | None
    percentage: int | None
    started_at: datetime
    submitted_at: datetime | None
