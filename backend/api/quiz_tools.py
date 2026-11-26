import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.models.video import ExamAttempt, Question, QuizGeneration, Transcript, Video
from backend.schemas.video import QuizConfiguration
from backend.services.structured_quiz import run_generation
from backend.utils.storage import VIDEO_DIR

router = APIRouter(prefix="/videos", tags=["Quiz configuration"])


def serialize_job(job):
    return {key: getattr(job, key) for key in ("id", "video_id", "quiz_version", "easy_count", "medium_count", "hard_count", "total_questions", "question_generation_mode", "generation_method", "status", "progress", "message", "created_at", "updated_at")}


@router.get("/quiz-settings")
def quiz_settings():
    return {"default": {"easy_count": 12, "medium_count": 12, "hard_count": 12},
            "max_questions": int(os.getenv("MAX_QUIZ_QUESTIONS", "60")),
            "ai_configured": bool(os.getenv("OLLAMA_MODEL", "").strip()),
            "baseline_difficulties": ["easy"], "visual_context_available": False}


@router.post("/{video_id}/generate", status_code=202)
def generate(video_id: int, payload: QuizConfiguration, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    video = db.query(Video).filter_by(id=video_id).with_for_update().first()
    if not video:
        raise HTTPException(404, "Video not found.")
    if not db.query(Transcript.id).filter_by(video_id=video_id).first():
        raise HTTPException(409, "Wait for the timestamped transcript before generating questions.")
    active = db.query(QuizGeneration).filter(QuizGeneration.video_id == video_id, QuizGeneration.status.in_(["queued", "running"])).first()
    if active:
        raise HTTPException(409, "A quiz is already being generated for this video.")
    if db.query(QuizGeneration).filter(QuizGeneration.status.in_(["queued", "running"])).count() >= int(os.getenv("MAX_GENERATION_JOBS", "2")):
        raise HTTPException(429, "Generation capacity is busy. Try again after another job completes.")
    job = QuizGeneration(video_id=video_id, total_questions=payload.total_questions, **payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    tasks.add_task(run_generation, job.id)
    return serialize_job(job)


@router.get("/generations/{job_id}")
def generation_status(job_id: int, db: Session = Depends(get_db)):
    job = db.get(QuizGeneration, job_id)
    if not job:
        raise HTTPException(404, "Quiz generation not found.")
    return serialize_job(job)


@router.get("/{video_id}/versions")
def quiz_versions(video_id: int, db: Session = Depends(get_db)):
    if not db.get(Video, video_id):
        raise HTTPException(404, "Video not found.")
    from sqlalchemy import func
    return [{"quiz_version": version, "total_questions": count} for version, count in db.query(Question.quiz_version, func.count(Question.id)).filter_by(video_id=video_id).group_by(Question.quiz_version).order_by(Question.quiz_version.desc()).all()]


@router.get("/{video_id}/generations")
def generation_history(video_id: int, db: Session = Depends(get_db)):
    return [serialize_job(job) for job in db.query(QuizGeneration).filter_by(video_id=video_id).order_by(QuizGeneration.id.desc()).limit(20).all()]


@router.get("/{video_id}/media", tags=["Media"])
def media(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found.")
    if video.playback_object_key:
        from backend.services.object_storage import signed_playback
        return RedirectResponse(signed_playback(video.playback_object_key), status_code=307)
    parsed = urlparse(video.file_path)
    if parsed.scheme == "https":
        allowed = {host.strip() for host in os.getenv("CLOUD_MEDIA_HOSTS", "").split(",") if host.strip()}
        if parsed.hostname not in allowed or parsed.username or parsed.password:
            raise HTTPException(403, "Cloud media host is not authorized.")
        return RedirectResponse(video.file_path, status_code=307)
    path = Path(video.file_path).resolve()
    if not path.is_relative_to(VIDEO_DIR.resolve()) or not path.is_file():
        raise HTTPException(404, "The original video file is unavailable on this server.")
    from backend.services.media_service import playback_path
    rendition = playback_path(video_id)
    if rendition.is_file():
        path = rendition
    return FileResponse(path, filename=path.name, content_disposition_type="inline")


@router.post("/attempts/{attempt_id}/practice/{question_id}")
def practice_answer(attempt_id: int, question_id: int, payload: dict[str, str], db: Session = Depends(get_db)):
    attempt = db.get(ExamAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Exam attempt not found.")
    if attempt.mode != "practice" or attempt.status != "in_progress":
        raise HTTPException(403, "Immediate explanations are available only during practice mode.")
    question = db.query(Question).filter_by(id=question_id, video_id=attempt.video_id, quiz_version=attempt.quiz_version).first()
    if not question:
        raise HTTPException(400, "Question does not belong to this attempt.")
    import json
    selected = payload.get("answer", "")
    if selected not in json.loads(question.options_json):
        raise HTTPException(400, "Select one of the question's options.")
    return {"question_id": question.id, "correct": selected == question.correct_answer,
            "selected_answer": selected, "correct_answer": question.correct_answer,
            "explanation": question.explanation, "evidence": question.evidence,
            "timestamp_seconds": question.timestamp_seconds, "difficulty": question.difficulty}


def recover_generation_jobs():
    """Mark jobs interrupted by the single-worker server restart; never fake completion."""
    from backend.database.database import SessionLocal
    with SessionLocal() as db:
        for job in db.query(QuizGeneration).filter(QuizGeneration.status.in_(["queued", "running"])).all():
            job.status = "interrupted"
            job.message = "Server restarted during generation. Regenerate to retry; earlier quizzes are unchanged."
        db.commit()
