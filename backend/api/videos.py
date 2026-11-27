import json, logging, os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path as ApiPath, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from backend.database.database import get_db
from backend.models.video import ExamAttempt, ExamResponse, Transcript, Video, Question
from backend.schemas.video import (
    ExamAttemptResultResponse,
    ExamAttemptHistoryItem,
    ExamAttemptStartRequest,
    ExamAttemptStartResponse,
    ExamAttemptSubmission,
    ExamSubmission,
    TranscriptOut,
    VideoOut,
    YouTubeRequest,
)
from backend.services.quiz_service import latest_quiz_version, question_versioning_available
from backend.services.video_service import process_video
from backend.utils.storage import VIDEO_DIR, unique_video_path
load_dotenv()
router = APIRouter(prefix="/videos", tags=["Videos"])
logger = logging.getLogger(__name__)
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))


def _quiz_questions(db: Session, video_id: int):
    """Load the latest quiz when versioning exists, or legacy rows otherwise."""
    if question_versioning_available(db):
        version = latest_quiz_version(db, video_id)
        questions = db.query(Question).filter(
            Question.video_id == video_id,
            Question.quiz_version == version,
        ).order_by(Question.id.asc()).all() if version is not None else []
        return version, questions

    # Select only columns present in the pre-versioning schema. Querying the
    # Question entity would select every mapped column, including quiz_version.
    questions = db.query(
        Question.id,
        Question.video_id,
        Question.question_text,
        Question.options_json,
        Question.correct_answer,
        Question.explanation,
        Question.difficulty,
        Question.timestamp_seconds,
    ).filter(Question.video_id == video_id).order_by(Question.id.asc()).all()
    return None, questions


def _require_attempt_schema(db: Session):
    tables = set(inspect(db.get_bind()).get_table_names())
    if not {"exam_attempts", "exam_responses"}.issubset(tables):
        raise HTTPException(
            status_code=503,
            detail=("Persistent exam attempts are temporarily unavailable because the database "
                    "is missing exam_attempts or exam_responses. Existing quizzes can still be graded, "
                    "but results will not be saved."),
        )

def validate_youtube_url(url: str):
    import re
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        raise HTTPException(status_code=400, detail="Please provide a valid YouTube watch, Shorts or youtu.be URL.")
    parts = parsed.path.strip("/").split("/")
    video_id = parts[0] if host.endswith("youtu.be") else (parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch" else (parts[1] if len(parts) == 2 and parts[0] in {"shorts", "embed"} else ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise HTTPException(status_code=400, detail="The YouTube URL must identify a video with a valid 11-character ID.")
    return "https://www.youtube.com/watch?v=" + video_id

@router.post("/upload", response_model=VideoOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...), rights_confirmed: bool = Form(False), db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(400, "Confirm that you own this content or have permission to process it.")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    stored_filename, destination = unique_video_path(extension)
    size = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_MB} MB limit.")
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    video = Video(source_type="upload", original_filename=(file.filename or "uploaded_video")[:255],
                  stored_filename=stored_filename, file_path=str(destination.resolve()), status="uploaded")
    try:
        db.add(video); db.commit(); db.refresh(video)
    except Exception:
        db.rollback(); destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save video metadata to the database.")
    background_tasks.add_task(process_video, video.id)
    return video

YOUTUBE_GUIDANCE = "Direct downloading of YouTube videos is not supported. Open the video on YouTube and provide an authorized transcript to generate your quiz."

@router.post("/youtube")
def submit_youtube(payload: YouTubeRequest):
    return {"source_url": validate_youtube_url(payload.url), "message": YOUTUBE_GUIDANCE}

@router.post("/{video_id}/retry")
def retry_youtube(video_id: int):
    raise HTTPException(410, YOUTUBE_GUIDANCE)

@router.post("/youtube/transcript", response_model=VideoOut, status_code=201)
async def youtube_transcript(url: str = Form(...), text: str = Form(""), rights_confirmed: bool = Form(False), file: UploadFile | None = File(None), db: Session = Depends(get_db)):
    from backend.services.transcript_import import parse_transcript
    if not rights_confirmed:
        raise HTTPException(400, "Confirm that you own this content or have permission to process it.")
    source_url = validate_youtube_url(url)
    if file and text.strip():
        raise HTTPException(400, "Provide either a transcript file or pasted text, not both.")
    extension = ".txt"
    if file:
        extension = Path(file.filename or "").suffix.lower()
        if extension not in {".txt", ".srt", ".vtt"}:
            raise HTTPException(400, "Choose a TXT, SRT or VTT transcript.")
        raw = await file.read(1000001)
        await file.close()
        if len(raw) > 1000000:
            raise HTTPException(413, "Transcript files must be under 1 MB.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "Save the transcript as UTF-8 text.")
    try:
        content, segments = parse_transcript(text, extension)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    video = Video(source_type="youtube", original_filename="YouTube transcript quiz", stored_filename="authorized-transcript", file_path="", source_url=source_url, status="ready_for_quiz")
    db.add(video); db.flush()
    db.add(Transcript(video_id=video.id, text=content, segments_json=json.dumps(segments), language=None))
    db.commit(); db.refresh(video)
    return video

@router.get("", response_model=list[VideoOut])
def list_videos(source_type: str = "upload", db: Session = Depends(get_db)):
    if source_type not in {"upload", "youtube"}:
        raise HTTPException(400, "Choose upload or youtube as the source type.")
    return db.query(Video).filter(Video.source_type == source_type).order_by(Video.created_at.desc()).limit(100).all()

@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    return video

@router.get("/{video_id}/transcript", response_model=TranscriptOut)
def get_transcript(video_id: int, db: Session = Depends(get_db)):
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found.")
        raise HTTPException(status_code=409, detail=f"Transcript not available yet. Current status: {video.status}")
    return {"video_id": video_id, "text": transcript.text, "language": transcript.language,
            "segments": json.loads(transcript.segments_json or "[]")}

@router.get("/{video_id}/quiz")
def get_quiz(video_id: int, db: Session = Depends(get_db), version: int | None = None):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    quiz_version, questions = _quiz_questions(db, video_id)
    if version is not None and question_versioning_available(db):
        quiz_version = version
        questions = db.query(Question).filter_by(video_id=video_id, quiz_version=version).order_by(Question.id).all()
        if not questions:
            raise HTTPException(404, "Quiz version not found.")
    configuration = None
    if "quiz_generations" in inspect(db.get_bind()).get_table_names():
        from backend.models.video import QuizGeneration
        from backend.api.quiz_tools import serialize_job
        job = db.query(QuizGeneration).filter_by(video_id=video_id, quiz_version=quiz_version, status="completed").first()
        configuration = serialize_job(job) if job else None
    if not questions and video.status not in {"completed", "completed_no_speech", "ready_for_quiz"}:
        raise HTTPException(status_code=409, detail=f"Quiz not available yet. Current status: {video.status}")
    return {"video_id": video_id, "status": video.status, "quiz_version": quiz_version,
            "configuration": configuration,
            "generation_method": getattr(questions[0], "generation_method", "baseline") if questions else None,
            "difficulty_counts": {level: sum(q.difficulty == level for q in questions) for level in ("easy", "medium", "hard")},
            "questions": [{"id": q.id, "video_id": q.video_id, "question": q.question_text,
                           "options": json.loads(q.options_json), "difficulty": q.difficulty,
                           "timestamp_seconds": q.timestamp_seconds, "source_timestamp": q.timestamp_seconds} for q in questions],
            "notice": "Questions are generated from the video transcript. Submit your answers to see your score and feedback."}

@router.post("/{video_id}/evaluate")
def evaluate_quiz(video_id: int, payload: ExamSubmission, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    quiz_version, questions = _quiz_questions(db, video_id)
    if not questions:
        raise HTTPException(status_code=409, detail=f"Quiz not available yet. Current status: {video.status}")
    question_ids = {question.id for question in questions}
    if set(payload.answers) - question_ids:
        raise HTTPException(status_code=400, detail="One or more submitted question IDs do not belong to this quiz.")

    results = []
    score = 0
    for question in questions:
        selected = payload.answers.get(question.id)
        correct = selected is not None and selected.strip().casefold() == question.correct_answer.strip().casefold()
        score += int(correct)
        results.append({"question_id": question.id, "selected_answer": selected,
                        "correct_answer": question.correct_answer, "correct": correct,
                        "explanation": question.explanation,
                        "feedback": ("Correct — nice work." if correct else
                                     f"Not quite. The correct answer is {question.correct_answer}.")})

    total = len(questions)
    percentage = round(score / total * 100)
    if percentage == 100:
        feedback = "Excellent work. You got every question right."
    elif percentage >= 80:
        feedback = "Strong understanding. Review the questions you missed to reinforce the details."
    elif percentage >= 50:
        feedback = "Good start. Review the explanations for missed questions, then try again."
    else:
        feedback = "Revisit the video or transcript, then retake the quiz to strengthen your understanding."
    return {"video_id": video_id, "quiz_version": quiz_version, "score": score, "total": total,
            "percentage": percentage, "feedback": feedback, "results": results}


def _attempt_questions(db: Session, attempt: ExamAttempt):
    return db.query(Question).filter(
        Question.video_id == attempt.video_id,
        Question.quiz_version == attempt.quiz_version,
    ).order_by(Question.id.asc()).all()


def _serialize_attempt_start(attempt: ExamAttempt, questions: list[Question]):
    return {
        "attempt_id": attempt.id,
        "video_id": attempt.video_id,
        "quiz_version": attempt.quiz_version,
        "status": attempt.status,
        "total_questions": attempt.total_questions,
        "started_at": attempt.started_at,
        "questions": [
            {
                "id": question.id,
                "video_id": question.video_id,
                "question": question.question_text,
                "options": json.loads(question.options_json),
                "difficulty": question.difficulty,
                "timestamp_seconds": question.timestamp_seconds,
            }
            for question in questions
        ],
        "mode": attempt.mode,
        "time_limit_seconds": attempt.time_limit_seconds,
        "expires_at": attempt.started_at + timedelta(seconds=attempt.time_limit_seconds) if attempt.time_limit_seconds else None,
        "notice": "Submit your answers to see your score and feedback.",
    }


def _serialize_attempt_result(attempt: ExamAttempt, responses: list[ExamResponse]):
    results = []
    for answer in sorted(responses, key=lambda row: row.question_id):
        results.append({
            "question_id": answer.question_id,
            "question": answer.question_text,
            "options": json.loads(answer.options_json),
            "selected_answer": answer.selected_answer,
            "correct_answer": answer.correct_answer,
            "correct": answer.is_correct,
            "explanation": answer.explanation,
            "difficulty": answer.difficulty,
            "timestamp_seconds": answer.timestamp_seconds,
            "evidence": answer.evidence,
            "feedback": (
                "Correct — nice work." if answer.is_correct
                else f"Not quite. The correct answer is {answer.correct_answer}."
            ),
        })
    return {
        "attempt_id": attempt.id,
        "video_id": attempt.video_id,
        "quiz_version": attempt.quiz_version,
        "status": attempt.status,
        "submitted_at": attempt.submitted_at,
        "score": attempt.score,
        "total": attempt.total_questions,
        "percentage": attempt.percentage,
        "feedback": attempt.feedback,
        "results": results,
        "incorrect": sum(not row.is_correct and row.selected_answer is not None for row in responses),
        "unanswered": sum(row.selected_answer is None for row in responses),
        "time_taken_seconds": max(0, int((attempt.submitted_at - attempt.started_at).total_seconds())),
        "difficulty_performance": {
            level: {
                "total": sum(row.difficulty == level for row in responses),
                "correct": sum(row.difficulty == level and row.is_correct for row in responses),
                "incorrect": sum(row.difficulty == level and not row.is_correct and row.selected_answer is not None for row in responses),
                "unanswered": sum(row.difficulty == level and row.selected_answer is None for row in responses),
            } for level in ("easy", "medium", "hard")
        },
    }


@router.post(
    "/{video_id}/attempts",
    response_model=ExamAttemptStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_exam_attempt(
    video_id: Annotated[int, ApiPath(gt=0)],
    payload: ExamAttemptStartRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        video = db.query(Video).filter(Video.id == video_id).with_for_update().first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found.")
        _require_attempt_schema(db)

        existing = db.query(ExamAttempt).filter(
            ExamAttempt.idempotency_key == payload.idempotency_key
        ).with_for_update().first()
        if existing:
            if existing.video_id != video_id:
                raise HTTPException(status_code=409, detail="Idempotency key is already used for another exam.")
            questions = _attempt_questions(db, existing)
            if not questions:
                raise HTTPException(status_code=409, detail="The quiz for this attempt is no longer available.")
            response.status_code = status.HTTP_200_OK
            return _serialize_attempt_start(existing, questions)

        quiz_version = payload.quiz_version or latest_quiz_version(db, video_id)
        questions = db.query(Question).filter(
            Question.video_id == video_id,
            Question.quiz_version == quiz_version,
        ).order_by(Question.id.asc()).all() if quiz_version is not None else []
        if not questions:
            if video.status not in {"completed", "completed_no_speech"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Quiz not available yet. Current status: {video.status}",
                )
            raise HTTPException(status_code=409, detail="No quiz questions are available for this video.")

        attempt = ExamAttempt(
            video_id=video_id,
            quiz_version=quiz_version,
            status="in_progress",
            total_questions=len(questions),
            idempotency_key=payload.idempotency_key,
            started_at=datetime.utcnow(),
            mode=payload.mode,
            time_limit_seconds=(payload.time_limit_seconds or max(60, len(questions) * 60)) if payload.mode == "exam" else None,
        )
        db.add(attempt)
        db.flush()
        db.commit()
        db.refresh(attempt)
        return _serialize_attempt_start(attempt, questions)
    except IntegrityError:
        db.rollback()
        # Concurrent retries can race between the idempotency lookup and insert.
        existing = db.query(ExamAttempt).filter(
            ExamAttempt.idempotency_key == payload.idempotency_key
        ).first()
        if existing and existing.video_id == video_id:
            questions = _attempt_questions(db, existing)
            if questions:
                response.status_code = status.HTTP_200_OK
                return _serialize_attempt_start(existing, questions)
        if existing:
            raise HTTPException(status_code=409, detail="Idempotency key is already used for another exam.")
        raise HTTPException(status_code=409, detail="Could not create exam attempt. Retry with the same idempotency key.")
    except Exception:
        db.rollback()
        raise


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=ExamAttemptResultResponse,
)
def submit_exam_attempt(
    attempt_id: Annotated[int, ApiPath(gt=0)],
    payload: ExamAttemptSubmission,
    db: Session = Depends(get_db),
):
    _require_attempt_schema(db)
    try:
        attempt = db.query(ExamAttempt).filter(
            ExamAttempt.id == attempt_id
        ).with_for_update().first()
        if not attempt:
            raise HTTPException(status_code=404, detail="Exam attempt not found.")
        if attempt.status == "completed":
            return _serialize_attempt_result(
                attempt,
                db.query(ExamResponse).filter(ExamResponse.attempt_id == attempt.id).all(),
            )
        if attempt.status != "in_progress":
            raise HTTPException(status_code=409, detail="This exam attempt cannot be submitted.")

        questions = _attempt_questions(db, attempt)
        if not questions:
            raise HTTPException(status_code=409, detail="The quiz for this attempt is no longer available.")
        allowed_ids = {question.id for question in questions}
        if set(payload.answers) - allowed_ids:
            raise HTTPException(
                status_code=400,
                detail="One or more submitted question IDs do not belong to this exam attempt.",
            )

        now = datetime.utcnow()
        if attempt.time_limit_seconds and now > attempt.started_at + timedelta(seconds=attempt.time_limit_seconds + 10):
            # Late submissions cannot replace answers after the server deadline.
            # Previously saved practice/exam results remain idempotent above.
            payload = ExamAttemptSubmission(answers={})
        for question in questions:
            selected = payload.answers.get(question.id)
            if selected is not None and selected.strip().casefold() not in {option.strip().casefold() for option in json.loads(question.options_json)}:
                raise HTTPException(400, "One or more answers are not among the question options.")
        score = 0
        response_rows = []
        for question in questions:
            selected = payload.answers.get(question.id)
            correct = (
                selected is not None
                and selected.strip().casefold() == question.correct_answer.strip().casefold()
            )
            score += int(correct)
            response_rows.append(ExamResponse(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=selected,
                is_correct=correct,
                answered_at=now if selected is not None else None,
                question_text=question.question_text,
                options_json=question.options_json,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                difficulty=question.difficulty,
                timestamp_seconds=question.timestamp_seconds,
                evidence=question.evidence,
            ))

        total = len(questions)
        percentage = round(score / total * 100)
        if percentage == 100:
            feedback = "Excellent work. You got every question right."
        elif percentage >= 80:
            feedback = "Strong understanding. Review the questions you missed to reinforce the details."
        elif percentage >= 50:
            feedback = "Good start. Review the explanations for missed questions, then try again."
        else:
            feedback = "Revisit the video or transcript, then retake the quiz to strengthen your understanding."

        db.add_all(response_rows)
        attempt.status = "completed"
        attempt.score = score
        attempt.percentage = percentage
        attempt.feedback = feedback
        attempt.submitted_at = now
        db.flush()
        db.commit()
        db.refresh(attempt)
        return _serialize_attempt_result(attempt, response_rows)
    except IntegrityError:
        db.rollback()
        latest_attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if latest_attempt and latest_attempt.status == "completed":
            saved_responses = db.query(ExamResponse).filter(
                ExamResponse.attempt_id == latest_attempt.id
            ).all()
            return _serialize_attempt_result(latest_attempt, saved_responses)
        raise HTTPException(status_code=409, detail="This exam attempt was already submitted or could not be saved.")
    except Exception:
        db.rollback()
        raise


@router.get(
    "/attempts/{attempt_id}",
    response_model=ExamAttemptResultResponse,
)
def get_exam_attempt_result(
    attempt_id: Annotated[int, ApiPath(gt=0)],
    db: Session = Depends(get_db),
):
    _require_attempt_schema(db)
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Exam attempt not found.")
    if attempt.status != "completed" or attempt.submitted_at is None:
        raise HTTPException(status_code=409, detail="Exam attempt has not been submitted.")
    if attempt.score is None or attempt.percentage is None or attempt.feedback is None:
        raise HTTPException(status_code=409, detail="Saved exam result is incomplete.")
    responses = db.query(ExamResponse).filter(ExamResponse.attempt_id == attempt.id).all()
    return _serialize_attempt_result(attempt, responses)


@router.get(
    "/{video_id}/attempts",
    response_model=list[ExamAttemptHistoryItem],
)
def list_video_exam_attempts(
    video_id: Annotated[int, ApiPath(gt=0)],
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    _require_attempt_schema(db)

    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.video_id == video_id
    ).order_by(ExamAttempt.started_at.desc(), ExamAttempt.id.desc()).all()
    return [
        {
            "attempt_id": attempt.id,
            "video_id": attempt.video_id,
            "quiz_version": attempt.quiz_version,
            "status": attempt.status,
            "total_questions": attempt.total_questions,
            "score": attempt.score,
            "percentage": attempt.percentage,
            "started_at": attempt.started_at,
            "submitted_at": attempt.submitted_at,
        }
        for attempt in attempts
    ]
