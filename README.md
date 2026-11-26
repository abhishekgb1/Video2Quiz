# Video2Quiz

Current development checkpoint: React/Vite quiz dashboard, configurable generation, timed exams, practice feedback, source playback and versioned database storage. See [implementation status](docs/implementation-status.md) for tested behavior and unfinished work. Cloud deployment is not complete.



## Included
- FastAPI backend with Swagger docs and Postman-ready endpoints
- MySQL and PostgreSQL persistence via SQLAlchemy and Alembic migrations
- Video upload with extension and size validation
- Public YouTube URL ingestion via yt-dlp
- FFmpeg audio extraction
- Whisper transcription with timestamped segments
- Baseline transcript-derived MCQs stored in MySQL
- Small React/Vite frontend to upload, track status, and view transcript/quiz

## Still to build
Authentication, a durable processing queue, live AI model configuration and validation, topic analytics, and production deployment remain unfinished. Timed exams and persistent attempts are implemented.
The MCQ generator here is an extractive baseline and must be reviewed before formal use.

## Requirements
Windows 10/11, Python 3.11, MySQL Server + Workbench, FFmpeg on PATH, Node.js 20+ for frontend.
Run `ffmpeg -version` to verify FFmpeg.

## 1. Create database in MySQL Workbench
Run:
```sql
CREATE DATABASE video2quiz CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Run Alembic migrations to create and update tables; application startup does not create them automatically.

## 2. Configure
Copy `.env.example` to `.env` in the project root and edit the MySQL credentials.
Do not commit `.env` or share your database password.

## 3. Backend setup (PowerShell, project root)
```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
If PowerShell blocks activation, run once:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Reopen the terminal and activate the environment.

## 4. Start backend
Ensure MySQL Server is running and FFmpeg works, then:
```powershell
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000/ and http://127.0.0.1:8000/docs

## 5. Start frontend (second terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open the Vite URL, normally http://localhost:5173.

## 6. Test with Postman
Upload:
- POST `http://127.0.0.1:8000/api/videos/upload`
- Body > form-data; key `file` set to File; select a supported video.

YouTube:
- POST `http://127.0.0.1:8000/api/videos/youtube`
- Body > raw > JSON: `{"url":"https://www.youtube.com/watch?v=VIDEO_ID"}`

Status/results:
- GET `/api/videos`
- GET `/api/videos/1`
- GET `/api/videos/1/transcript`
- GET `/api/videos/1/quiz`
Use the actual video ID returned by the API. Keep the backend running while processing.

## Troubleshooting
- MySQL connection refused: start MySQL Server and check port 3306.
- Access denied: check username/password and grants.
- `ffmpeg` not recognized: add the folder containing `ffmpeg.exe` (e.g. `C:\\ffmpeg\\bin`) to Windows PATH and restart VS Code.
- Whisper can be slow. Set `WHISPER_MODEL=tiny` in `.env` for an initial test.
- YouTube downloads require yt-dlp's JavaScript challenge solver and a supported JavaScript runtime. Install the project requirements in the backend venv with `python -m pip install -r requirements.txt`; Node.js 22+ is enabled automatically when it is on PATH. Restart the backend after installing or updating dependencies. The app retries transient requests and shows a shorter troubleshooting message; technical details remain in the backend terminal.
- If YouTube requires you to sign in, close the browser first, then set `YOUTUBE_COOKIES_FROM_BROWSER=chrome` in `.env` (or `edge` / `firefox`) and restart the backend. This reads your browser's YouTube session; keep `.env` private. Cookie access is not a workaround for content you are not authorized to access.
- YouTube can still block automated downloads based on video restrictions, account checks, or network/firewall rules. In that case, upload a video file you have permission to use. Follow YouTube's terms.

## Database migrations

Alembic is the schema lifecycle mechanism. The API startup no longer calls `Base.metadata.create_all()`. Set `DATABASE_URL` in the local environment or `.env` file; credentials are not stored in `alembic.ini` or migration scripts.

For a **fresh database**, create an empty database, then run from the project root:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

The baseline creates the existing `videos`, `transcripts`, and `questions` schema, then the next migration adds `questions.quiz_version`. The following additive revision creates `exam_attempts` and `exam_responses`.

Quiz generation now preserves earlier question rows and assigns each successful non-empty generation the next per-video version. Quiz retrieval and grading use only the latest stored version; grading rejects submitted IDs from older versions. The quiz response adds a top-level `quiz_version` integer (or `null` when no quiz exists) while retaining its existing fields. Existing questions become version 1 through the migration; the first successful regeneration after migration will therefore be version 2.

For the **existing MySQL database**, do not run `upgrade` against it until its live schema has been compared with `0001_existing_schema_baseline.py` and all tables, columns, types, nullability, keys, and indexes match. Resolve any differences with a reviewed migration or a separately reviewed schema change. Only after reconciliation should an operator explicitly stamp the baseline revision (`0001_existing_schema`) and then apply later migrations. Stamping is not automatic and does not inspect or modify the schema. This repository does not run `stamp` as part of startup.

MySQL may commit DDL implicitly. If a migration fails, inspect the schema and data before retrying or downgrading; do not assume automatic rollback. The question-version downgrade removes only its index and column, while the baseline downgrade is deliberately blocked because dropping its tables would delete application data.


## Free cloud database (Neon)

The deployment configuration uses an external Neon Free PostgreSQL database rather than provisioning a Render database. MySQL remains supported for local development. Set `DATABASE_URL` in the backend environment only; never put it in frontend variables or source control. Use the connection string from the Neon console with `sslmode=require`. Existing PostgreSQL URLs are normalized to the installed psycopg driver.

For a new empty database, run `python -m alembic upgrade head` and verify with `python -m alembic current`. Use a direct (non-pooler) connection for migrations. Back up and review existing databases before schema changes. No local records are copied automatically.

The Video2Quiz project was provisioned in the connected free Neon organization in Singapore. All three existing migrations were applied through `0003_exam_attempts_responses`. A temporary verification row passed committed insertion, retrieval over a new connection, update, and retrieval over another new connection; that row was then removed.

Manage the database at https://console.neon.tech/app/projects/ancient-tooth-57453741 . Keep the organization on Free; do not enable paid upgrades. Free quotas can suspend database availability when exhausted. Uploaded video/audio files are separate from PostgreSQL: the current Render `/tmp/video2quiz` storage is ephemeral and still needs a durable media solution before production deployment.


### Windows processing dependencies

Start the backend with `.\start-backend.ps1` after installing requirements into `.venv`. The script refreshes PATH and checks FFmpeg and Whisper before serving requests. FFmpeg is installed for this Windows user in `%LOCALAPPDATA%\Video2Quiz\bin` (bundled Windows binary from imageio-ffmpeg); this folder is on the user PATH. Restart existing terminals/services after PATH changes. The first transcription downloads the configured Whisper model and requires internet access. `WHISPER_MODEL=tiny` is configured locally for CPU processing.
