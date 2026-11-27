# Verification report

Updated: 27 November 2026 (Asia/Kolkata).

## Automated checks

- `python -m pytest -q`: **63 passed**, one upstream Starlette/httpx deprecation warning.
- `npm run build`: **passed** (Vite production bundle).
- GitHub Actions passed for checkpoint `7dc4894`; subsequent commits have their own workflow results.
- Tests use isolated databases and provider fixtures where indicated. They do not prove live AI question quality.

## Actual deployed workflow

Frontend: https://video2quiz.vercel.app

Backend and Swagger: https://video2quiz.onrender.com/docs

| Check | Executed result |
| --- | --- |
| Vercel page, backend liveness and database readiness | HTTP 200 |
| Production CORS | Exact Vercel origin accepted |
| Educational video upload through production UI | Accepted as test video 5 |
| FFmpeg processing on Render Free | Completed; browser playback rendition created |
| Whisper transcription on Render Free | Real English transcript: 590 characters, 8 timestamped segments |
| Configuration before generation | Processing stopped at `ready_for_quiz`; no unsolicited questions |
| Custom Easy generation through production UI | Four questions saved as version 1 from that cloud transcript |
| Practice feedback | Correct and incorrect answers produced corresponding feedback |
| Backend scoring | Test attempt 5 saved 1 correct, 1 incorrect, 2 unanswered: 25% |
| Difficulty-wise results | Easy score 1/4; zero Medium and Hard questions reported accurately |
| Zero-total and over-limit requests | Live backend rejected both with HTTP 422 |
| Unsupported default generation without AI | Explicitly refused; earlier question IDs unchanged |
| Regeneration | Version 2 created; version 1 and the saved result remained accessible |
| Storage records | Neon inspection confirmed original/playback keys, transcript, both quiz versions and response snapshots |
| Restart persistence | Render startup logs confirm a new backend instance on 27 November; saved video/transcript/quiz/result records remained available |
| Timed exam on production UI | A separate one-minute exam auto-submitted and saved the correct score |
| Exam answer restrictions | No correct answer or explanation displayed before submission |
| Mobile and tablet layout | 390px and 768px layouts had no horizontal overflow |
| Theme | Light/Dark toggled; Light preference survived refresh; Light hero contrast fixed |
| Console | No console errors captured during the verified production quiz workflow |

## Media delivery regression

The Windows network currently fails to resolve direct Neon database/storage hosts. The deployed backend remains connected. Earlier direct signed storage retrieval passed, but a repeat request on the Windows network failed at DNS resolution.

The cloud media API now streams from private storage through the backend address instead of redirecting the browser to a Neon hostname. Added automated tests verify HTTP 206 byte-range delivery, correct range headers, closure of the upstream streaming body, and rejection of malformed ranges before any storage request. Production verification of this new route is recorded after deployment.

## Limits and incomplete checks

- No AI model is configured. Live Medium/Hard generation and a genuine 36-question AI quiz remain unverified. The 12/12/12 persistence test uses a provider fixture; the production baseline supports Easy recall only.
- The baseline can generate cloze questions. It is not a reviewed assessment-quality AI generator.
- OCR/visual fusion, authentication/user isolation, and durable processing-job recovery are incomplete.
- YouTube embed restrictions and full-screen playback still need dedicated browser checks.
- Vercel CLI deployment works. GitHub auto-deploy linking requires the owner to add a GitHub Login Connection in Vercel.
- Current Windows DNS prevents direct local connections to Neon; no global DNS/network settings were changed.
- No paid resources were enabled. Free-host cold starts and resource/bandwidth quotas apply.
