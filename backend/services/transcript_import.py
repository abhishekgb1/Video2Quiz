"""Import user-provided transcripts without contacting YouTube."""
import html
import re


def parse_transcript(text, extension):
    if len(text) > 200000:
        raise ValueError("Transcript exceeds the 200,000-character limit.")
    text = text.strip()
    if not text:
        raise ValueError("Provide an authorized transcript file or paste its text.")
    if extension == ".txt":
        segments = [{"text": part.strip()} for part in re.split(r"\n\s*\n|(?<=[.!?])\s+", text) if part.strip()]
        return text, segments
    stamp = r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})"
    pattern = re.compile(r"^" + stamp + r"\s+-->\s+" + stamp + r"(?:\s+.*)?$")
    segments = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = pattern.fullmatch(line.strip())
            if not match:
                continue
            values = match.groups()
            times = []
            for offset in (0, 4):
                hours, minutes, seconds, millis = values[offset:offset + 4]
                if int(minutes) > 59 or int(seconds) > 59:
                    raise ValueError("Transcript contains an invalid cue timestamp.")
                times.append(int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000)
            if times[1] <= times[0] or (segments and times[0] < segments[-1]["start"]):
                raise ValueError("Transcript cues must have increasing start times and positive durations.")
            body = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[index + 1:]))).strip()
            if body:
                segments.append({"start": times[0], "end": times[1], "text": body})
            break
    if not segments:
        raise ValueError("No valid timestamped cues found. Check the SRT/VTT format, or paste plain text.")
    return " ".join(segment["text"] for segment in segments), segments
