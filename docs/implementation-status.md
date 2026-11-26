# Development checkpoint

Saved on 26 November 2026 at the user's request. This is a development checkpoint, not a completed production release.

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

- Before this checkpoint, 60 automated backend tests passed, including existing benchmark tests. Final checkpoint test output is reported in the accompanying chat.
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
- The private Neon media bucket accepts uploads, but the issued write-scoped credential returned AccessDenied for reads/listing and signed retrieval. Cloud playback is not verified. Configure a credential with explicit storage read and write scopes and repeat persistence tests before relying on cloud media. Do not upload private content until access behavior is verified.
- Existing local videos were not migrated to cloud storage. Render Free local files are ephemeral.
- In-app browser media playback was unavailable; the saved video was verified in desktop Edge. YouTube embedded playback, full-screen behavior, mobile/tablet layouts, and cloud video playback still need complete browser checks.
- Backend exam API restrictions are tested. Final browser timer/auto-submit testing is not complete.
- Authentication and user-level data isolation are not implemented. Treat this as a single-user development/demo app, not a private multi-user examination service.
- GitHub Actions configuration is included; its remote execution must be checked after pushing.
- Render and Vercel deployment are not completed. No paid hosting services were enabled. Vercel authorization/project selection remains to be completed.

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
