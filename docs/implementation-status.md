# Development checkpoint

Updated on 26 November 2026. The free demo is deployed; advanced AI and multi-user security remain unfinished.

## Implemented

- Default configuration of 12 Easy, 12 Medium and 12 Hard questions; custom independent counts, dynamic totals, and a configurable server limit.
- Background quiz-generation jobs with status/progress, version history, and atomic publication of complete distributions. Failed requests preserve older quizzes.
- Optional structured Ollama generation with Pydantic validation, transcript evidence, timestamps, distinct options, and duplicate detection. The original Easy baseline remains available.
- Practice feedback, timed examination mode, backend grading, saved attempts, question navigation, difficulty filters, and difficulty-wise result summaries.
- Source video player above the quiz, native seek/speed controls, timestamp navigation, and optional YouTube IFrame API integration.
- Browser-compatible MP4 renditions preserve original uploaded/downloaded files. Existing YouTube downloads were MPEG-TS despite their `.mp4` names; renditions fix desktop playback.
- Persistent Light/Dark preference and shared theme variables.
- Additive Alembic revisions `0004_quiz_configuration` and `0005_cloud_media`. Both were tested on an isolated Neon branch before applying them to the main database. Local backups are excluded from Git.
- Optional private S3-compatible media integration and a CPU-only Docker setup. Secrets remain in environment variables.

## Executed verification

- The checkpoint passed 60 automated tests; the resumed work adds a regression check that processing waits for user configuration. Final test output is reported in the accompanying chat.
- Frontend production build passed.
- Browser: four Easy questions generated from the real saved transcript and persisted as a new version; prior version remained accessible.
- Browser: practice feedback, submission, saved results, and difficulty filtering exercised.
- Browser: Light Mode persisted across refresh. Dark and Light layouts inspected.
- Desktop Edge: actual associated video played; timestamp navigation started playback near the requested 00:27 position. Playback state confirmed advancing time, a 288.9-second duration, and ready state 4.
- Main database migrations reached `0005_cloud_media`; no existing records were deleted or overwritten.

## Unfinished / unverified

- No Ollama model is configured. Live Medium/Hard generation and a real AI-generated 36-question quiz have not been verified. Exact 12/12/12 database distribution is covered by a provider-fixture test, not a live model test. Without AI, requests requiring Medium/Hard fail explicitly instead of relabeling baseline questions.
- The fallback is a simple extractive Easy generator and can produce cloze questions; question quality and transcript transcription errors need review before formal assessment.
- No OCR or visual-context analysis is implemented; questions currently use transcript evidence only.
- Private Neon storage is now verified with explicit read/write scopes: writes, fresh-client signed retrieval, partial byte reads, and denial of anonymous access. Credentials stay outside Git. The earlier write-only credential did not grant read access in the live service.
- Existing local videos were not migrated to cloud storage. Render Free local files are ephemeral.
- Cloud video metadata and timestamp seeking were exercised in the production browser. Mobile 390px question navigation and theme layouts were checked without horizontal overflow. YouTube embedded playback and full-screen mode still need dedicated checks.
- Production-browser timed examination passed: answers stayed hidden, the one-minute timer auto-submitted, grading/difficulty analysis were correct, and the result persisted across refresh.
- Authentication and user-level data isolation are not implemented. Treat this as a single-user development/demo app, not a private multi-user examination service.
- GitHub Actions configuration is included; its remote execution must be checked after pushing.
- Vercel and Render are deployed on free resources. The backend database-readiness endpoint passed. Vercel CLI deployments work, but GitHub auto-deploy linking is blocked until the owner adds a GitHub Login Connection in their Vercel account. No paid services were enabled.

## Local commands

From the project directory, with `.env` configured:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\start-backend.ps1
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Validation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```

Stop local servers with Ctrl+C in their terminals. Local secrets, database backups, uploaded media, virtual environments, generated builds and logs are ignored by Git.


## Live demo

- Frontend: https://video2quiz.vercel.app
- Backend: https://video2quiz.onrender.com
- API documentation: https://video2quiz.onrender.com/docs
- Database readiness: https://video2quiz.onrender.com/health/ready
- Public source repository: https://github.com/abhishekgb1/Video2Quiz

A newly generated educational clip was actually transcribed locally with Whisper, uploaded to private Neon media storage, and used to generate four Easy questions. Server grading matched independently calculated database answers; the saved result was retrieved successfully. Production browser tests used this shared database and cloud media. Production-side video processing is checked separately; reading an already-processed clip does not prove cloud transcription works.

Video processing now stops at `ready_for_quiz` after transcription, allowing configuration before generation. Silent videos retain `completed_no_speech`. Successful generation marks the video completed, and regeneration preserves earlier versions.
