"""
Tests for text_normalizer adapter - word timing alignment and tokenization.
"""
import pytest
from app.adapters.text_normalizer import (
    normalize_text,
    tokenize_words,
    get_word_at_char_position,
    find_word_index,
    align_word_timings,
    estimate_word_timings,
)


class TestNormalizeText:
    """Tests for normalize_text function."""
    
    def test_empty_string(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""
    
    def test_smart_quotes_replaced(self):
        text = 'He said \u201cHello\u201d and \u2018goodbye\u2019'
        result = normalize_text(text)
        assert '"Hello"' in result
        assert "'goodbye'" in result
    
    def test_multiple_spaces_collapsed(self):
        text = "Hello    world   test"
        result = normalize_text(text)
        assert result == "Hello world test"
    
    def test_line_endings_normalized(self):
        text = "Line1\r\nLine2\rLine3"
        result = normalize_text(text)
        assert result == "Line1\nLine2\nLine3"
    
    def test_em_dash_replaced(self):
        text = "Hello\u2014world"  # em dash
        result = normalize_text(text)
        assert result == "Hello-world"
    
    def test_ellipsis_replaced(self):
        text = "Wait\u2026"  # ellipsis
        result = normalize_text(text)
        assert result == "Wait..."

    def test_preserves_marker_tokens_exactly(self):
        from app.adapters.marker_tokens import format_marker_token

        mid = "6f2c9f7a-1234-5678-9abc-def012345678"
        token = format_marker_token(mid)
        text = f'He said  “Hello”   {token}   world'
        result = normalize_text(text)

        # Token must survive normalization unchanged
        assert token in result
        # And spacing should still be normalized around it (single spaces on both sides)
        assert f"\"Hello\" {token} world" in result


class TestTokenizeWords:
    """Tests for tokenize_words function."""
    
    def test_empty_string(self):
        assert tokenize_words("") == []
    
    def test_simple_sentence(self):
        words = tokenize_words("Hello world")
        assert len(words) == 2
        assert words[0] == (0, 5, "Hello")
        assert words[1] == (6, 11, "world")
    
    def test_with_punctuation(self):
        words = tokenize_words("Hello, world!")
        # Should have Hello and world (punctuation filtered)
        word_texts = [w[2] for w in words]
        assert "Hello" in word_texts
        assert "world" in word_texts
    
    def test_contractions(self):
        words = tokenize_words("don't can't won't")
        word_texts = [w[2] for w in words]
        assert "don't" in word_texts
        assert "can't" in word_texts
    
    def test_numbers(self):
        words = tokenize_words("I have 42 apples")
        word_texts = [w[2] for w in words]
        assert "42" in word_texts

    def test_tokenize_words_skips_marker_tokens_by_default(self):
        from app.adapters.marker_tokens import format_marker_token

        mid = "6f2c9f7a-1234-5678-9abc-def012345678"
        token = format_marker_token(mid)
        text = f"{token}Hello world"

        words = tokenize_words(text)
        word_texts = [w[2] for w in words]
        assert "Hello" in word_texts
        assert "world" in word_texts
        # The UUID should NOT appear as a tokenized "word"
        assert mid not in word_texts


class TestGetWordAtCharPosition:
    """Tests for get_word_at_char_position function."""
    
    def test_finds_word(self):
        text = "Hello world"
        result = get_word_at_char_position(text, 2)  # 'l' in Hello
        assert result == (0, 5, "Hello")
    
    def test_second_word(self):
        text = "Hello world"
        result = get_word_at_char_position(text, 8)  # 'r' in world
        assert result == (6, 11, "world")
    
    def test_position_in_space_returns_none(self):
        text = "Hello world"
        result = get_word_at_char_position(text, 5)  # space
        assert result is None


class TestFindWordIndex:
    """Tests for find_word_index function."""
    
    def test_finds_exact_match(self):
        text = "Hello world test"
        idx = find_word_index(text, 6, 11)  # "world"
        assert idx == 1
    
    def test_not_found(self):
        text = "Hello world"
        idx = find_word_index(text, 100, 105)  # out of range
        assert idx == -1


class TestAlignWordTimings:
    """Tests for align_word_timings function - the main fix."""
    
    def test_empty_alignment(self):
        result = align_word_timings("Hello world", None)
        assert result == []
        
        result = align_word_timings("Hello world", {})
        assert result == []
    
    def test_mismatched_lengths(self):
        alignment = {
            "characters": ["H", "e", "l", "l", "o"],
            "character_start_times_seconds": [0.0, 0.1],  # Too short
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
        result = align_word_timings("Hello", alignment)
        assert result == []  # Should reject mismatched data
    
    def test_simple_alignment(self):
        """Test basic word timing extraction."""
        # "Hello world" with character-level timing
        alignment = {
            "characters": list("Hello world"),
            "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
        }
        result = align_word_timings("Hello world", alignment)
        
        assert len(result) == 2
        
        # Check Hello
        hello = result[0]
        assert hello["word"] == "Hello"
        assert hello["charStart"] == 0
        assert hello["charEnd"] == 5
        assert hello["startTime"] == 0.0
        assert hello["endTime"] == 0.5  # End of 'o' in Hello
        
        # Check world
        world = result[1]
        assert world["word"] == "world"
        assert world["charStart"] == 6
        assert world["charEnd"] == 11
        assert world["startTime"] == 0.6
        assert world["endTime"] == 1.1
    
    def test_repeated_words(self):
        """Test that repeated words get correct sequential timings."""
        # "the cat and the dog" - "the" appears twice
        text = "the cat and the dog"
        chars = list(text)
        n = len(chars)
        start_times = [i * 0.1 for i in range(n)]
        end_times = [(i + 1) * 0.1 for i in range(n)]
        
        alignment = {
            "characters": chars,
            "character_start_times_seconds": start_times,
            "character_end_times_seconds": end_times,
        }
        
        result = align_word_timings(text, alignment)
        
        # Should have 5 words: the, cat, and, the, dog
        assert len(result) == 5
        
        # First "the" at position 0
        assert result[0]["word"] == "the"
        assert result[0]["startTime"] == 0.0
        
        # Second "the" at position 12 (after "the cat and ")
        assert result[3]["word"] == "the"
        assert result[3]["startTime"] == pytest.approx(1.2, rel=0.01)  # 12 * 0.1
    
    def test_case_insensitive_fallback(self):
        """Test case-insensitive matching when exact match fails."""
        # ElevenLabs might return different casing
        text = "Hello World"
        alignment = {
            "characters": list("hello world"),  # lowercase from TTS
            "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
        }
        
        result = align_word_timings(text, alignment)
        
        # Should still find both words via case-insensitive fallback
        assert len(result) == 2
        assert result[0]["word"] == "Hello"
        assert result[1]["word"] == "World"


class TestEstimateWordTimings:
    """Tests for estimate_word_timings fallback function."""
    
    def test_empty_text(self):
        result = estimate_word_timings("", 10.0)
        assert result == []
    
    def test_zero_duration(self):
        result = estimate_word_timings("Hello world", 0.0)
        assert result == []
    
    def test_proportional_distribution(self):
        """Test that timing is distributed proportionally by character count."""
        text = "Hi there"  # 2 chars + 5 chars
        result = estimate_word_timings(text, 7.0)  # 7 seconds total
        
        assert len(result) == 2
        
        # "Hi" is 2/7 of total chars, so should get 2 seconds
        assert result[0]["word"] == "Hi"
        assert result[0]["startTime"] == pytest.approx(0.0)
        assert result[0]["endTime"] == pytest.approx(2.0)
        
        # "there" is 5/7 of total chars, so should get 5 seconds
        assert result[1]["word"] == "there"
        assert result[1]["startTime"] == pytest.approx(2.0)
        assert result[1]["endTime"] == pytest.approx(7.0)
    
    def test_includes_char_positions(self):
        """Test that charStart/charEnd are correctly set."""
        text = "Hello world"
        result = estimate_word_timings(text, 10.0)
        
        assert result[0]["charStart"] == 0
        assert result[0]["charEnd"] == 5
        assert result[1]["charStart"] == 6
        assert result[1]["charEnd"] == 11

