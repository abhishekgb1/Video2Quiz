from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.api.videos import router as videos_router
from backend.api.quiz_tools import router as quiz_tools_router
from backend.database.database import engine  # noqa: F401; retained for app/test integrations

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only inspect installed schemas; legacy databases remain readable.
    from sqlalchemy import inspect
    if os.getenv("RECOVER_GENERATION_JOBS") == "1" and "quiz_generations" in inspect(engine).get_table_names():
        from backend.api.quiz_tools import recover_generation_jobs
        recover_generation_jobs()
    yield

app = FastAPI(title="Video2Quiz API", description="Turn educational videos into timestamped practice quizzes.",
              version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(quiz_tools_router, prefix="/api")
app.include_router(videos_router, prefix="/api")

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "version": "0.5.0"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    from sqlalchemy import text
    from fastapi import HTTPException
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable.")
    return {"status": "ready", "database": "connected"}


@app.get("/", tags=["Health"])
def root():
    frontend_index = Path(os.getenv("FRONTEND_DIST_DIR", "frontend/dist")) / "index.html"
    if frontend_index.is_file():
        return FileResponse(frontend_index)
    return {"message": "Video2Quiz API is running", "status": "healthy", "version": "0.5.0"}


frontend_dist = Path(os.getenv("FRONTEND_DIST_DIR", "frontend/dist"))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
