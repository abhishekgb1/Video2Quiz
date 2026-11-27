import json
import pytest
from test_api import client, create_processed_video
from backend.database import database
from backend.models.video import Transcript, Video
from backend.services.transcript_import import parse_transcript

SOURCE = "Photosynthesis converts sunlight into stored chemical energy in plants. Evaporation changes liquid water into vapor when heat is supplied. Gravity attracts masses and keeps planets moving around the sun. Enzymes accelerate chemical reactions without being consumed during reactions."


@pytest.mark.parametrize("url", ["https://youtu.be/_t3pBsFMBVU", "https://www.youtube.com/shorts/_t3pBsFMBVU", "https://www.youtube.com/watch?v=_t3pBsFMBVU"])
def test_authorized_plain_text_quiz_has_no_invented_timestamps(client, monkeypatch, url):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    upload_id, _ = create_processed_video()
    response = client.post("/api/videos/youtube/transcript", data={"url": url, "text": SOURCE, "rights_confirmed": "true"})
    assert response.status_code == 201
    video_id = response.json()["id"]
    assert [v["id"] for v in client.get("/api/videos").json()] == [upload_id]
    assert [v["id"] for v in client.get("/api/videos?source_type=youtube").json()] == [video_id]
    transcript = client.get(f"/api/videos/{video_id}/transcript").json()
    assert all("start" not in item for item in transcript["segments"])
    job = client.post(f"/api/videos/{video_id}/generate", json={"easy_count": 2, "medium_count": 0, "hard_count": 0, "question_generation_mode": "custom"})
    assert job.status_code == 202
    quiz = client.get(f"/api/videos/{video_id}/quiz").json()
    assert len(quiz["questions"]) == 2
    assert all(q["timestamp_seconds"] is None for q in quiz["questions"])
    with database.SessionLocal() as db:
        assert db.query(Transcript).filter_by(video_id=video_id).one().text == SOURCE


@pytest.mark.parametrize("extension,content,start", [
    (".srt", "1\n00:00:12,500 --> 00:00:18,000\n" + SOURCE, 12.5),
    (".vtt", "WEBVTT\n\n00:12.500 --> 00:18.000\n" + SOURCE, 12.5),
])
def test_timestamped_transcript_file(client, extension, content, start):
    response = client.post("/api/videos/youtube/transcript", data={"url": "https://youtu.be/_t3pBsFMBVU", "rights_confirmed": "true"}, files={"file": ("lesson" + extension, content.encode(), "text/plain")})
    assert response.status_code == 201
    segments = client.get(f"/api/videos/{response.json()['id']}/transcript").json()["segments"]
    assert segments[0]["start"] == start


def test_import_rejects_missing_permission_invalid_urls_and_invalid_files(client):
    assert client.post("/api/videos/upload", files={"file": ("video.mp4", b"video", "video/mp4")}).status_code == 400
    assert client.post("/api/videos/youtube/transcript", data={"url": "https://youtu.be/_t3pBsFMBVU", "text": SOURCE}).status_code == 400
    for url in ["https://youtube.com.evil.org/watch?v=_t3pBsFMBVU", "https://youtube.com/", "javascript:alert(1)", "https://youtu.be/invalid"]:
        assert client.post("/api/videos/youtube", json={"url": url}).status_code == 400
    assert client.post("/api/videos/youtube/transcript", data={"url": "https://youtu.be/_t3pBsFMBVU", "rights_confirmed": "true"}, files={"file": ("bad.srt", b"no valid cues", "text/plain")}).status_code == 400
    with pytest.raises(ValueError):
        parse_transcript("1\n00:00:20,000 --> 00:00:10,000\nInvalid cue", ".srt")


def test_legacy_failed_youtube_record_is_preserved_with_helpful_guidance(client):
    with database.SessionLocal() as db:
        video = Video(source_type="youtube", stored_filename="pending", file_path="", source_url="https://youtu.be/_t3pBsFMBVU", status="failed", error_message="Old download error")
        db.add(video); db.commit(); db.refresh(video)
        video_id = video.id
    assert client.get("/api/videos").json() == []
    assert client.get(f"/api/videos/{video_id}").json()["error_message"] == "Old download error"
    for suffix in ["transcript", "quiz"]:
        response = client.get(f"/api/videos/{video_id}/{suffix}")
        assert response.status_code == 409
        assert "authorized transcript" in response.json()["detail"]
    assert client.get(f"/api/videos/{video_id}/media").status_code == 410
