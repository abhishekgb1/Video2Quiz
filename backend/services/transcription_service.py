import json, os, subprocess
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from backend.utils.storage import AUDIO_DIR, TRANSCRIPT_DIR
load_dotenv()


@lru_cache(maxsize=2)
def _load_whisper_model(model_name: str):
    import whisper
    return whisper.load_model(model_name)

def extract_audio(video_path: Path, video_id: int) -> Path:
    output_path = AUDIO_DIR / f"video_{video_id}.wav"
    command = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
               "-acodec", "pcm_s16le", str(output_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg not found. Install it and ensure ffmpeg.exe is on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Audio extraction timed out.") from exc
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"FFmpeg audio extraction failed: {(result.stderr or 'Unknown error')[-1200:]}")
    return output_path

def transcribe_audio(audio_path: Path, video_id: int) -> dict:
    try:
        model = _load_whisper_model(os.getenv("WHISPER_MODEL", "tiny"))
    except ImportError as exc:
        raise RuntimeError("Whisper is not installed. Run pip install -r requirements.txt.") from exc
    result = model.transcribe(str(audio_path), fp16=False, verbose=False)
    payload = {"video_id": video_id, "language": result.get("language"),
               "text": (result.get("text") or "").strip(),
               "segments": [{"start": round(float(s.get("start", 0)), 2),
                             "end": round(float(s.get("end", 0)), 2),
                             "text": str(s.get("text", "")).strip()} for s in result.get("segments", [])]}
    (TRANSCRIPT_DIR / f"video_{video_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def extract_visual_text(video_path: Path, video_id: int, duration_seconds: int | None = None) -> list[dict]:
    """Sample a bounded set of frames and OCR readable slide text when available."""
    if os.getenv("ENABLE_VISUAL_OCR", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return []
    try:
        import cv2
        import pytesseract
    except ImportError:
        return []
    executable = os.getenv("TESSERACT_CMD")
    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 0
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = duration_seconds or (frame_count / fps if fps > 0 else 0)
        if duration <= 0:
            return []
        interval = max(5, int(os.getenv("OCR_SAMPLE_INTERVAL_SECONDS", "30")))
        max_frames = max(1, min(120, int(os.getenv("OCR_MAX_FRAMES", "120"))))
        sample_times = list(range(0, int(duration), interval))[:max_frames]
        results, seen = [], set()
        for timestamp in sample_times:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            scale = min(1.0, 1280 / max(width, height))
            if scale < 1:
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            text = " ".join(pytesseract.image_to_string(gray, config="--psm 6").split())
            normalized = " ".join(text.casefold().split())
            if len(text) < 8 or normalized in seen:
                continue
            seen.add(normalized)
            results.append({"timestamp_seconds": timestamp, "text": text[:2000]})
        return results
    finally:
        capture.release()
