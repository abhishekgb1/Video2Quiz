from backend.services.quiz_service import generate_baseline_questions

def test_baseline_generator_returns_questions():
    transcript = {"text": "Neural networks learn patterns from data. Training adjusts weights to reduce error. Validation checks how well a model generalizes.",
                  "segments": [{"start": 1, "text": "Neural networks learn patterns from data."},
                               {"start": 5, "text": "Training adjusts weights to reduce error."},
                               {"start": 9, "text": "Validation checks how well a model generalizes."}]}
    questions = generate_baseline_questions(transcript, 3)
    assert questions
    assert all(len(q["options"]) == 4 for q in questions)
    assert all(q["correct_answer"] in q["options"] for q in questions)
    assert all(not option.startswith("Option") for q in questions for option in q["options"])


def test_generator_skips_questions_without_real_distractors():
    transcript = {
        "text": "Neural neural neural networks networks networks patterns patterns patterns neural.",
        "segments": [{"start": 0, "text": "Neural neural neural networks networks networks patterns patterns patterns neural."}],
    }
    assert generate_baseline_questions(transcript, 5) == []


def test_generator_uses_timestamped_visual_evidence():
    transcript = {
        "text": "Neural networks learn patterns from data during supervised training. Optimization improves model performance over repeated batches.",
        "segments": [{"start": 100, "text": "Optimization improves model performance over repeated batches."}],
        "visual_text": [{
            "timestamp_seconds": 42,
            "text": "Neural networks learn patterns from data during supervised training.",
        }],
    }
    questions = generate_baseline_questions(transcript, 1)
    assert len(questions) == 1
    assert questions[0]["timestamp_seconds"] == 42
    assert "slide text" in questions[0]["question_text"]
    assert "slide text states" in questions[0]["explanation"]
