import uuid

import pytest


def test_format_and_parse_marker_token_roundtrip():
    from app.adapters.marker_tokens import format_marker_token, parse_marker_tokens

    mid = str(uuid.uuid4())
    token = format_marker_token(mid)
    assert token.startswith("⟦M:")
    assert token.endswith("⟧")

    text = f"Hello {token} world"
    tokens = parse_marker_tokens(text)
    assert len(tokens) == 1
    assert tokens[0].marker_id == mid.lower()
    assert text[tokens[0].start : tokens[0].end] == token


def test_contains_marker_tokens_true_false():
    from app.adapters.marker_tokens import contains_marker_tokens, format_marker_token

    assert contains_marker_tokens("no tokens here") is False
    assert contains_marker_tokens(format_marker_token(str(uuid.uuid4()))) is True


def test_compute_marker_time_from_word_timings_prefers_word_to_the_right():
    from app.adapters.marker_tokens import compute_marker_time_from_word_timings, format_marker_token

    mid = str(uuid.uuid4())
    token = format_marker_token(mid)
    # Token at start; anchor word should be the first word to the right.
    text = f"{token}Hello world"
    token_len = len(token)

    word_timings = [
        {"charStart": token_len, "charEnd": token_len + 5, "startTime": 1.0, "endTime": 1.2, "word": "Hello"},
        {"charStart": token_len + 6, "charEnd": token_len + 11, "startTime": 2.0, "endTime": 2.2, "word": "world"},
    ]

    t = compute_marker_time_from_word_timings(text, mid, word_timings)
    assert t == pytest.approx(1.0)


def test_compute_marker_time_from_word_timings_fallbacks_to_last_word_before():
    from app.adapters.marker_tokens import compute_marker_time_from_word_timings, format_marker_token

    mid = str(uuid.uuid4())
    token = format_marker_token(mid)
    # Token at end; fallback should use last word before (endTime preferred).
    text = f"Hello world{token}"

    word_timings = [
        {"charStart": 0, "charEnd": 5, "startTime": 1.0, "endTime": 1.1, "word": "Hello"},
        {"charStart": 6, "charEnd": 11, "startTime": 2.0, "endTime": 2.5, "word": "world"},
    ]

    t = compute_marker_time_from_word_timings(text, mid, word_timings)
    assert t == pytest.approx(2.5)


