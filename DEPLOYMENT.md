# Free demo deployment

The existing FastAPI application runs in a CPU-only Docker image on Render Free. React/Vite runs on Vercel. Neon Free PostgreSQL stores transcripts, questions, versions and results. A private Neon object-storage bucket stores new originals and browser playback renditions. Existing local videos are not moved automatically.

## Current endpoints

- Website: https://video2quiz.vercel.app
- API: https://video2quiz.onrender.com/api
- Swagger: https://video2quiz.onrender.com/docs
- Liveness: `/health`; database readiness: `/health/ready`.

## Configuration

Keep `DATABASE_URL` and the `AWS_*` storage credentials in Render environment variables only. Configure `MEDIA_BUCKET` for private durable media. `VIDEO2QUIZ_DATA_DIR` is temporary working storage, not the permanent media store. `WHISPER_MODEL=tiny`, one generation job, and a 100 MB upload limit are configured for the free host. The Docker image installs CPU-only PyTorch and limits CPU threads.

Vercel's `VITE_API_BASE_URL` is `https://video2quiz.onrender.com/api`. This is a public API address, not a secret. Backend CORS permits the exact production frontend origin and localhost development origins.

The optional `OLLAMA_MODEL` integration is not configured. A Render service cannot reach an Ollama server bound to the developer's localhost. Do not configure a localhost AI endpoint in cloud production and expect it to connect to the Windows computer. Without an available provider, generation uses a clearly identified Easy-only baseline and rejects unsupported Medium/Hard distributions.

## Updates

Run tests and the frontend build before committing. Push the reviewed source to `main`; Render auto-deploys that branch and runs additive Alembic migrations at startup. Back up existing databases and validate migrations on a Neon branch before changing the main schema. Do not stamp or downgrade existing databases automatically.

Vercel was deployed using its authenticated CLI from the `frontend` directory:

```powershell
cd frontend
npm exec --yes --package=vercel -- vercel deploy --project video2quiz --yes --prod
```

The API environment variable is saved in Vercel for Production, Preview and Development. GitHub linking currently requires the owner to add GitHub under their Vercel account's Login Connections. After that connection exists, connect the repository and select `frontend` as the Root Directory for Git deployments; use `npm ci`, `npm run build`, and `dist`.

## Limits

Render Free has 512 MB RAM, limited CPU, cold starts, and an ephemeral local disk. Cloud transcription must be verified against those limits; do not infer successful processing from a healthy API. Free included bandwidth/build quotas apply. Neon free quotas also apply. No paid upgrades were enabled.

This remains a shared single-user demo. Authentication, user-level isolation, durable processing recovery and a full advanced-AI quality evaluation are not complete. Do not use it for private multi-user examinations yet. Source-linked questions can inherit transcription errors and should be reviewed before formal assessment.
