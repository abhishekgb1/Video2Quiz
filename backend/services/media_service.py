"""Create a seekable browser rendition without changing the original upload."""
import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from backend.utils.storage import VIDEO_DIR


def playback_path(video_id):
    return VIDEO_DIR / f"playback_{video_id}.mp4"


def prepare_browser_video(source: Path, video_id: int):
    destination = playback_path(video_id)
    if destination.is_file():
        return destination
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(source)], capture_output=True, text=True, timeout=30)
    streams = [line for line in probe.stderr.splitlines() if "Stream #" in line]
    video = next((line for line in streams if "Video:" in line), "")
    audio = next((line for line in streams if "Audio:" in line), "")
    if not video:
        raise RuntimeError("The source contains no playable video stream.")
    # MP4 naming does not prove MP4 contents: YouTube HLS often produces MPEG-TS.
    compatible = bool(re.search(r"Video: h264\b", video)) and (not audio or "Audio: aac" in audio)
    temp = destination.with_name(f"playback_{video_id}_{uuid4().hex}.tmp.mp4")
    codecs = ["-c", "copy"] if compatible else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    command = ["ffmpeg", "-nostdin", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", *codecs, "-movflags", "+faststart", str(temp)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=3600)
        if result.returncode or not temp.is_file():
            raise RuntimeError("Could not prepare the browser playback rendition.")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination
