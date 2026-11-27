import json
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from test_api import client, create_processed_video
from backend.database import database
from backend.models.video import ExamAttempt, Question, QuizGeneration, Transcript, Video
from backend.schemas.video import QuizConfiguration
from backend.services import structured_quiz


def source_data():
    sentences = [
        "Photosynthesis converts sunlight into stored chemical energy in plants.",
        "Mitochondria release usable energy through cellular respiration in cells.",
        "Evaporation changes liquid water into vapor when heat is supplied.",
        "Gravity attracts masses and keeps planets moving around the sun.",
        "Enzymes accelerate chemical reactions without being consumed during reactions.",
        "Insulation reduces the transfer of thermal energy between objects.",
        "Diffusion moves particles from higher concentration toward lower concentration.",
        "Friction opposes relative motion between surfaces that touch each other.",
    ]
    return {"text": " ".join(sentences), "segments": [{"start": i * 12, "text": sentence} for i, sentence in enumerate(sentences)]}


def add_transcript(video_id):
    source = source_data()
    with database.SessionLocal() as db:
        db.add(Transcript(video_id=video_id, text=source["text"], segments_json=json.dumps(source["segments"])))
        db.commit()
    return source


def test_configuration_defaults_and_resource_limits(monkeypatch):
    assert QuizConfiguration().total_questions == 36
    for counts in [(0, 0, 0), (-1, 1, 1), (61, 0, 0)]:
        with pytest.raises(ValidationError):
            QuizConfiguration(easy_count=counts[0], medium_count=counts[1], hard_count=counts[2], question_generation_mode="custom")
    with pytest.raises(ValidationError):
        QuizConfiguration(easy_count=True)
    with pytest.raises(ValidationError):
        QuizConfiguration(easy_count=1)
    assert QuizConfiguration(easy_count=0, medium_count=2, hard_count=0, question_generation_mode="custom").total_questions == 2
    monkeypatch.setenv("MAX_QUIZ_QUESTIONS", "2")
    with pytest.raises(ValidationError):
        QuizConfiguration(easy_count=3, medium_count=0, hard_count=0, question_generation_mode="custom")


def test_custom_generation_saves_exact_counts_evidence_and_preserves_versions(client, monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    video_id, old = create_processed_video()
    add_transcript(video_id)
    response = client.post(f"/api/videos/{video_id}/generate", json={"easy_count": 4, "medium_count": 0, "hard_count": 0, "question_generation_mode": "custom"})
    assert response.status_code == 202
    job = client.get(f"/api/videos/generations/{response.json()['id']}").json()
    assert job["status"] == "completed"
    assert job["total_questions"] == 4 and job["generation_method"] == "baseline"
    current = client.get(f"/api/videos/{video_id}/quiz").json()
    assert current["quiz_version"] == 2
    assert current["difficulty_counts"] == {"easy": 4, "medium": 0, "hard": 0}
    assert all(len(set(q["options"])) == 4 for q in current["questions"])
    assert all("correct_answer" not in q and "explanation" not in q for q in current["questions"])
    previous = client.get(f"/api/videos/{video_id}/quiz?version=1").json()
    assert [q["id"] for q in previous["questions"]] == old[1]
    with database.SessionLocal() as db:
        assert all(q.evidence and q.timestamp_seconds is not None for q in db.query(Question).filter_by(video_id=video_id, quiz_version=2))


def test_default_refuses_to_fake_medium_hard_and_keeps_old_quiz(client, monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    video_id, old = create_processed_video()
    add_transcript(video_id)
    response = client.post(f"/api/videos/{video_id}/generate", json={})
    status = client.get(f"/api/videos/generations/{response.json()['id']}").json()
    assert status["status"] == "insufficient_content"
    assert "Easy recall" in status["message"]
    assert client.get(f"/api/videos/{video_id}/quiz").json()["quiz_version"] == 1


def test_default_job_persists_exact_distribution_with_provider_fixture(client, monkeypatch):
    """Exercise saving/quotas, not a claim of a live AI model quality test."""
    video_id, _ = create_processed_video()
    source = add_transcript(video_id)
    def provider_fixture(transcript, counts, progress):
        items = []
        for level, count in counts.items():
            for index in range(count):
                items.append({"question_text": f"Fixture {level} question {index}", "options": ["A", "B", "C", "D"], "correct_answer": "A", "explanation": "Provider contract fixture for database distribution tests.", "difficulty": level, "timestamp_seconds": 0, "evidence": source["segments"][0]["text"]})
        return items, "ollama", None
    monkeypatch.setattr(structured_quiz, "build_questions", provider_fixture)
    job = client.post(f"/api/videos/{video_id}/generate", json={}).json()
    assert client.get(f"/api/videos/generations/{job['id']}").json()["status"] == "completed"
    quiz = client.get(f"/api/videos/{video_id}/quiz").json()
    assert len(quiz["questions"]) == 36
    assert quiz["difficulty_counts"] == {"easy": 12, "medium": 12, "hard": 12}


def test_incomplete_provider_distribution_never_publishes_partial_quiz(client, monkeypatch):
    video_id, _ = create_processed_video()
    add_transcript(video_id)
    monkeypatch.setattr(structured_quiz, "build_questions", lambda *_: ([], "ollama", None))
    job = client.post(f"/api/videos/{video_id}/generate", json={}).json()
    assert client.get(f"/api/videos/generations/{job['id']}").json()["status"] == "insufficient_content"
    assert client.get(f"/api/videos/{video_id}/quiz").json()["quiz_version"] == 1


def test_generation_rejects_missing_transcript_and_invalid_counts(client):
    video_id, _ = create_processed_video()
    assert client.post(f"/api/videos/{video_id}/generate", json={}).status_code == 409
    assert client.post(f"/api/videos/{video_id}/generate", json={"easy_count": 0, "medium_count": 0, "hard_count": 0, "question_generation_mode": "custom"}).status_code == 422


def test_processing_waits_for_user_configuration_before_generating(client, monkeypatch, tmp_path):
    from backend.services import video_service, media_service, object_storage
    source = source_data()
    monkeypatch.setattr(video_service, "extract_audio", lambda *_: tmp_path / "audio.wav")
    monkeypatch.setattr(video_service, "transcribe_audio", lambda *_: {**source, "language": "en"})
    monkeypatch.setattr(media_service, "prepare_browser_video", lambda *_: tmp_path / "playback.mp4")
    monkeypatch.setattr(object_storage, "enabled", lambda: False)
    response = client.post("/api/videos/upload", files={"file": ("lesson.mp4", b"test source", "video/mp4")})
    identifier = response.json()["id"]
    video_service.process_video(identifier)
    with database.SessionLocal() as db:
        assert db.get(Video, identifier).status == "ready_for_quiz"
        assert db.query(Transcript).filter_by(video_id=identifier).one().text == source["text"]
        assert db.query(Question).filter_by(video_id=identifier).count() == 0
        assert db.query(QuizGeneration).filter_by(video_id=identifier).count() == 0
    assert client.get(f"/api/videos/{identifier}/quiz").json()["questions"] == []


def test_practice_explanations_are_forbidden_during_timed_exam(client):
    video_id, ids = create_processed_video()
    exam = client.post(f"/api/videos/{video_id}/attempts", json={"idempotency_key": "timed-enhanced", "mode": "exam", "time_limit_seconds": 60}).json()
    assert exam["expires_at"] and "correct_answer" not in exam["questions"][0]
    assert client.post(f"/api/videos/attempts/{exam['attempt_id']}/practice/{ids[1][0]}", json={"answer": "A"}).status_code == 403
    practice = client.post(f"/api/videos/{video_id}/attempts", json={"idempotency_key": "practice-enhanced", "mode": "practice"}).json()
    feedback = client.post(f"/api/videos/attempts/{practice['attempt_id']}/practice/{ids[1][0]}", json={"answer": "B"})
    assert feedback.status_code == 200 and feedback.json()["correct"] is False
    assert feedback.json()["correct_answer"] == "A"


def test_difficulty_results_and_snapshot_persistence(client):
    video_id, ids = create_processed_video({1: [("Easy item", ["A", "B"], "A"), ("Medium item", ["C", "D"], "C"), ("Hard item", ["E", "F"], "F")]})
    with database.SessionLocal() as db:
        for qid, difficulty in zip(ids[1], ["easy", "medium", "hard"]):
            q = db.get(Question, qid); q.difficulty = difficulty; q.timestamp_seconds = 45; q.evidence = "Original evidence"
        db.commit()
    attempt = client.post(f"/api/videos/{video_id}/attempts", json={"idempotency_key": "analysis-enhanced", "mode": "practice"}).json()
    response = client.post(f"/api/videos/attempts/{attempt['attempt_id']}/submit", json={"answers": {str(ids[1][0]): "A", str(ids[1][1]): "D"}}).json()
    assert (response["score"], response["incorrect"], response["unanswered"], response["percentage"]) == (1, 1, 1, 33)
    assert response["difficulty_performance"]["easy"]["correct"] == 1
    assert response["difficulty_performance"]["medium"]["incorrect"] == 1
    assert response["difficulty_performance"]["hard"]["unanswered"] == 1
    with database.SessionLocal() as db:
        q = db.get(Question, ids[1][0]); q.difficulty = "hard"; q.evidence = "Changed source metadata"; db.commit()
    saved = client.get(f"/api/videos/attempts/{attempt['attempt_id']}").json()
    assert saved == response
    assert saved["results"][0]["evidence"] == "Original evidence"


def test_expired_exam_cannot_accept_late_answers(client):
    video_id, ids = create_processed_video()
    attempt = client.post(f"/api/videos/{video_id}/attempts", json={"idempotency_key": "expired-enhanced", "time_limit_seconds": 60}).json()
    with database.SessionLocal() as db:
        row = db.get(ExamAttempt, attempt["attempt_id"]); row.started_at = datetime.utcnow() - timedelta(minutes=3); db.commit()
    result = client.post(f"/api/videos/attempts/{attempt['attempt_id']}/submit", json={"answers": {str(ids[1][0]): "A"}}).json()
    assert result["score"] == 0 and result["unanswered"] == 1


def test_media_rejects_paths_outside_media_root(client, tmp_path):
    video_id, _ = create_processed_video()
    with database.SessionLocal() as db:
        video = db.get(Video, video_id); video.file_path = str(tmp_path / "private.env"); db.commit()
    assert client.get(f"/api/videos/{video_id}/media").status_code == 404


def test_cloud_video_streams_range_and_closes_storage_body(client, monkeypatch):
    import io
    from types import SimpleNamespace
    from botocore.response import StreamingBody
    from backend.services import object_storage
    video_id, _ = create_processed_video()
    with database.SessionLocal() as db:
        db.get(Video, video_id).playback_object_key = f"videos/{video_id}/playback/test.mp4"
        db.commit()
    stream = io.BytesIO(b"test")
    calls = []
    def get_object(**parameters):
        calls.append(parameters)
        return {"Body": StreamingBody(stream, 4), "ContentLength": 4,
                "ContentRange": "bytes 0-3/12", "ContentType": "video/mp4"}
    monkeypatch.setenv("MEDIA_BUCKET", "test-media")
    monkeypatch.setattr(object_storage, "client", lambda: SimpleNamespace(get_object=get_object))
    response = client.get(f"/api/videos/{video_id}/media", headers={"Range": "bytes=0-3"})
    assert response.status_code == 206 and response.content == b"test"
    assert response.headers["content-range"] == "bytes 0-3/12"
    assert response.headers["accept-ranges"] == "bytes"
    assert calls[0]["Range"] == "bytes=0-3" and stream.closed


def test_cloud_video_rejects_malformed_range_before_storage_request(client, monkeypatch):
    from backend.services import object_storage
    video_id, _ = create_processed_video()
    with database.SessionLocal() as db:
        db.get(Video, video_id).playback_object_key = f"videos/{video_id}/playback/test.mp4"
        db.commit()
    def forbidden_client():
        raise AssertionError("Malformed range must not reach cloud storage")
    monkeypatch.delenv("MEDIA_BUCKET", raising=False)
    monkeypatch.setattr(object_storage, "client", forbidden_client)
    assert client.get(f"/api/videos/{video_id}/media", headers={"Range": "bytes=0-1,4-5"}).status_code == 416


def sample_generated(difficulty="easy"):
    source = source_data()
    evidence = [{"segment_index": 0, "quote": source["segments"][0]["text"]}]
    if difficulty == "hard": evidence.append({"segment_index": 1, "quote": source["segments"][1]["text"]})
    return {"question_text": "Which process converts sunlight into chemical energy?", "options": ["Photosynthesis", "Evaporation", "Diffusion", "Friction"], "correct_answer": "Photosynthesis", "difficulty": difficulty, "explanation": "Photosynthesis stores sunlight as chemical energy, as stated explicitly in the source.", "cognitive_skill": {"easy": "recall", "medium": "application", "hard": "multi_step"}[difficulty], "evidence": evidence}


@pytest.mark.parametrize("fault", ["duplicates", "evidence", "difficulty", "answer", "hard_single_source"])
def test_structured_validation_rejects_ungrounded_or_mislabeled_questions(fault):
    item = sample_generated("hard" if fault == "hard_single_source" else "easy")
    if fault == "duplicates": item["options"][1] = item["options"][0].upper()
    if fault == "evidence": item["evidence"][0]["quote"] = "This invented evidence does not exist in the original source."
    if fault == "difficulty": item["cognitive_skill"] = "analysis"
    if fault == "answer": item["correct_answer"] = "Unknown"
    if fault == "hard_single_source": item["evidence"] = item["evidence"][:1]
    batch = structured_quiz.GeneratedBatch(questions=[item])
    with pytest.raises(ValueError): structured_quiz.validate_batch(batch, source_data()["segments"], item["difficulty"], [])


def test_structured_validator_accepts_grounded_question_and_rejects_near_duplicate():
    item = sample_generated()
    batch = structured_quiz.GeneratedBatch(questions=[item])
    accepted = structured_quiz.validate_batch(batch, source_data()["segments"], "easy", [])
    assert accepted[0]["timestamp_seconds"] == 0
    with pytest.raises(ValueError): structured_quiz.validate_batch(batch, source_data()["segments"], "easy", accepted)
