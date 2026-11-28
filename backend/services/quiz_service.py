import json, re
from collections import Counter
from sqlalchemy import func, inspect
from backend.models.video import Question, Video

STOPWORDS = set("about after again also among because before being between could does during each from have having into more most other over same some such than that their there these they this those through under very what when where which while with would your will then them were been has had are was and for not but you the can our use used using like its".split())


class QuizVersioningUnavailable(RuntimeError):
    """Raised when generation needs a schema column that is not installed."""


def question_versioning_available(db):
    return any(
        column["name"] == "quiz_version"
        for column in inspect(db.get_bind()).get_columns("questions")
    )

def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip().split()) >= 7]

def generate_baseline_questions(transcript: dict, count: int = 5):
    # Extractive baseline, not an LLM; review question quality before formal use.
    candidates = []
    for seg in transcript.get("segments") or []:
        sentence = str(seg.get("text", "")).strip()
        if len(sentence.split()) >= 7:
            candidates.append((sentence, int(float(seg.get("start", 0))), "speech"))
    for item in transcript.get("visual_text") or []:
        sentence = str(item.get("text", "")).strip()
        if len(sentence.split()) >= 7:
            candidates.append((sentence, int(float(item.get("timestamp_seconds", 0))), "visual"))
    if not candidates:
        candidates = [(s, None, "speech") for s in _sentences(transcript.get("text", ""))]
    candidates.sort(key=lambda item: (item[1] is None, item[1] if item[1] is not None else 0))
    all_context = " ".join([transcript.get("text", "")] + [str(item.get("text", "")) for item in transcript.get("visual_text") or []])
    words = [w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", all_context)]
    frequency = Counter(w for w in words if w not in STOPWORDS)
    questions, seen = [], set()
    for sentence, timestamp, source in candidates:
        if len(questions) >= count:
            break
        meaningful = [w for w in re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", sentence) if w.lower() not in STOPWORDS]
        if len(meaningful) < 3:
            continue
        target = max(meaningful, key=lambda w: (frequency[w.lower()], len(w)))
        if target.lower() in seen:
            continue
        seen.add(target.lower())
        distractors = []
        for word, _ in frequency.most_common():
            if word.lower() != target.lower() and word.lower() not in {d.lower() for d in distractors}:
                distractors.append(word)
            if len(distractors) == 3:
                break
        # Do not invent placeholder answers: those make a question look usable
        # while providing no meaningful distractors. Skip it if the transcript
        # does not contain enough distinct terms.
        if len(distractors) < 3:
            continue
        options = [target] + distractors
        shift = len(questions) % 4
        options = options[shift:] + options[:shift]
        masked = re.sub(rf"\b{re.escape(target)}\b", "_____", sentence, count=1, flags=re.IGNORECASE)
        source_label = "slide text" if source == "visual" else "transcript"
        questions.append({"question_text": f"According to the {source_label}, which term completes this statement? {masked}",
                          "options": options, "correct_answer": target,
                          "explanation": f'The video {source_label} states: “{sentence}”',
                          "difficulty": "easy", "timestamp_seconds": timestamp})
    return questions

def persist_questions(db, video_id: int, transcript: dict, count: int = 5):
    if not question_versioning_available(db):
        raise QuizVersioningUnavailable(
            "Quiz generation is temporarily unavailable because the database is missing "
            "questions.quiz_version. Existing quizzes can still be viewed and graded."
        )
    items = generate_baseline_questions(transcript, count)
    if not items:
        return 0

    try:
        # MySQL locks this per-video row so concurrent workers serialize version
        # allocation. SQLite safely exercises the transaction, though its
        # with_for_update implementation is a no-op.
        video = db.query(Video).filter(Video.id == video_id).with_for_update().first()
        if video is None:
            raise ValueError(f"Cannot generate questions for missing video {video_id}.")
        current_version = db.query(Question.quiz_version).filter(
            Question.video_id == video_id
        ).order_by(Question.quiz_version.desc()).limit(1).with_for_update().scalar() or 0
        next_version = current_version + 1

        db.add_all([
            Question(video_id=video_id, quiz_version=next_version,
                     question_text=item["question_text"],
                     options_json=json.dumps(item["options"], ensure_ascii=False),
                     correct_answer=item["correct_answer"], explanation=item["explanation"],
                     difficulty=item["difficulty"], timestamp_seconds=item["timestamp_seconds"])
            for item in items
        ])
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(items)


def latest_quiz_version(db, video_id: int) -> int | None:
    return db.query(func.max(Question.quiz_version)).filter(
        Question.video_id == video_id
    ).scalar()

def serialize_question(q: Question):
    return {"id": q.id, "video_id": q.video_id, "question": q.question_text,
            "options": json.loads(q.options_json), "correct_answer": q.correct_answer,
            "explanation": q.explanation, "difficulty": q.difficulty,
            "timestamp_seconds": q.timestamp_seconds}
