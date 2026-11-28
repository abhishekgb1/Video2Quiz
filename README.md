# Video2Quiz

Video2Quiz turns an educational video into a timestamped transcript and a small extractive multiple-choice quiz. The React/Vite dashboard talks to a FastAPI API; SQLAlchemy and Alembic manage MySQL/PostgreSQL/SQLite data.

## Processing pipeline

1. Validate and save an uploaded video, or submit a supported public YouTube URL through yt-dlp.
2. FFmpeg converts the audio to mono 16 kHz WAV.
3. OpenAI Whisper creates a transcript with speech segment start/end times. `WHISPER_MODEL=tiny` is the fast default for local/free CPU hosting; use `base` or another installed Whisper model if you prefer higher accuracy and have the memory/time available. The first run downloads the model.
4. OpenCV samples frames at the configured interval and Tesseract OCR extracts readable slide text with timestamps. OCR is optional when its Python modules are unavailable; set `ENABLE_VISUAL_OCR=false` to disable it.
5. Transcript and OCR snippets are persisted separately and both can contribute to extractive quiz generation. This baseline generator is not an LLM: it masks a repeated content term, chooses three other terms from the source as distractors, and skips candidates that lack four distinct terms. Review its questions before formal assessment.
6. Quiz attempts and answer snapshots are stored in SQLAlchemy models and evaluated by the API.
7. The React dashboard displays source, processing progress, transcript, questions, and saved attempts. While processing, it polls the API every 2.5 seconds.

OCR is sampled rather than exhaustive: defaults inspect one frame every 30 seconds and at most 120 frames. It is intended for lecture slides and screen text, not a complete visual understanding system. YouTube processing follows yt-dlp's access behavior and can fail for restricted videos.

## Local setup (Windows)

Requirements: Python 3.11, Node.js 20+, FFmpeg on PATH, and Tesseract OCR. OpenCV is installed with the Python requirements. Whisper runs on CPU unless configured otherwise.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `DATABASE_URL` in `.env` to the database URL you intend to use. SQLite is suitable for a local/free single-user run, for example:

```dotenv
DATABASE_URL=sqlite:///data/video2quiz.db
```

For MySQL use a SQLAlchemy driver URL such as `mysql+pymysql://...`; for PostgreSQL use `postgresql+psycopg://...`. Keep credentials in `.env` and out of source control. On Windows, if Tesseract is not on PATH, set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`.

Run additive migrations and start the backend:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. API docs are at http://127.0.0.1:8000/docs and readiness is http://127.0.0.1:8000/health/ready.

## Configuration

- `DATABASE_URL`: SQLAlchemy database URL (required).
- `VIDEO2QUIZ_DATA_DIR`: source videos, extracted audio, and transcript artifacts (default `./data`).
- `MAX_UPLOAD_MB`: maximum upload size (default 500).
- `WHISPER_MODEL`: Whisper model name; default `tiny` for CPU responsiveness.
- `ENABLE_VISUAL_OCR`: enable/disable frame OCR (default true).
- `OCR_SAMPLE_INTERVAL_SECONDS`: sample interval (default 30 seconds; minimum effective interval is 5 seconds).
- `OCR_MAX_FRAMES`: upper bound on frames sampled per video (default 120, hard-capped at 120).
- `TESSERACT_CMD`: optional full path to the Tesseract executable.
- `CORS_ORIGINS`: comma-separated frontend origins.

## API quick start

- `POST /api/videos/upload` — multipart file upload; returns the video record while background processing continues.
- `POST /api/videos/youtube` — JSON `{"url":"https://www.youtube.com/watch?v=..."}`.
- `GET /api/videos` and `GET /api/videos/{id}` — video status and progress.
- `GET /api/videos/{id}/transcript` — speech transcript, timestamped speech segments, and timestamped OCR snippets.
- `GET /api/videos/{id}/quiz` — latest quiz version.
- `POST /api/videos/{id}/attempts`, `POST /api/videos/attempts/{id}/submit`, `GET /api/videos/{id}/attempts` — persistent exam attempts and results.

## Tests and deployment

```powershell
$env:FRONTEND_DIST_DIR='data/empty-test-frontend'
.\.venv\Scripts\python.exe -m pytest -q
cd frontend; npm run build
```

The Dockerfile installs FFmpeg and Tesseract, builds the frontend, applies Alembic migrations, and starts FastAPI. Production should set `DATABASE_URL`, `CORS_ORIGINS`, `VIDEO2QUIZ_DATA_DIR`, and resource-appropriate `WHISPER_MODEL` values in the host environment. Local disk is ephemeral on many free hosts, so a persistent disk or object storage is required if uploaded media must survive service restarts.
