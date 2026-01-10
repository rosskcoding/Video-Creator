"""
Text Normalization Utility
Prepares text for TTS and extracts word positions for animation triggers.

EPIC A Enhancement:
Preserves marker tokens (⟦M:uuid⟧) during normalization and tokenization.
"""
import re
import unicodedata
from typing import List, Tuple, Optional


TOKENIZATION_VERSION = 2  # Bumped for marker token support

# Marker token pattern from marker_tokens.py (duplicated to avoid circular import)
MARKER_TOKEN_PATTERN = re.compile(
    r'⟦M:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})⟧',
    re.IGNORECASE
)

def normalize_text(text: str, preserve_marker_tokens: bool = True) -> str:
    """
    Normalize text for consistent processing:
    - Normalize unicode (NFC)
    - Replace smart quotes with straight quotes
    - Replace multiple spaces with single space
    - Trim whitespace
    - Normalize line endings
    - PRESERVE marker tokens (⟦M:uuid⟧) if preserve_marker_tokens=True
    
    Args:
        text: Text to normalize
        preserve_marker_tokens: If True, marker tokens are preserved exactly
    """
    if not text:
        return ""
    
    # Extract and temporarily replace marker tokens
    marker_tokens = []
    if preserve_marker_tokens:
        for match in MARKER_TOKEN_PATTERN.finditer(text):
            marker_tokens.append((match.start(), match.end(), match.group()))
        
        # Replace tokens with placeholders (reverse order to maintain positions)
        modified_text = text
        for i, (start, end, token) in enumerate(reversed(marker_tokens)):
            placeholder = f'\x00MKRTOK{len(marker_tokens) - 1 - i}\x00'
            modified_text = modified_text[:start] + placeholder + modified_text[end:]
        text = modified_text
    
    # Unicode normalization
    normalized = unicodedata.normalize("NFC", text)
    
    # Replace smart quotes
    replacements = {
        "\u2018": "'",  # Left single quotation
        "\u2019": "'",  # Right single quotation
        "\u201C": '"',  # Left double quotation
        "\u201D": '"',  # Right double quotation
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        "\u2026": "...",  # Ellipsis
        "\u00A0": " ",  # Non-breaking space
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    
    # Normalize line endings
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    
    # Collapse multiple spaces (but preserve newlines)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    
    # Remove leading/trailing whitespace per line
    lines = normalized.split("\n")
    lines = [line.strip() for line in lines]
    normalized = "\n".join(lines)
    
    # Trim overall
    normalized = normalized.strip()
    
    # Restore marker tokens
    if preserve_marker_tokens and marker_tokens:
        for i, (_, _, token) in enumerate(marker_tokens):
            placeholder = f'\x00MKRTOK{i}\x00'
            normalized = normalized.replace(placeholder, token)

        # IMPORTANT (EPIC A): Do not modify marker tokens or their surrounding spacing.
        # We only normalize generic whitespace; tokens remain as-is.
    
    return normalized


def contains_marker_tokens(text: str) -> bool:
    """Check if text contains marker tokens (⟦M:uuid⟧)."""
    return bool(MARKER_TOKEN_PATTERN.search(text))


def extract_marker_ids_from_text(text: str) -> List[str]:
    """Extract all marker UUIDs from text."""
    return [m.group(1).lower() for m in MARKER_TOKEN_PATTERN.finditer(text)]


def tokenize_words(text: str, skip_marker_tokens: bool = True) -> List[Tuple[int, int, str]]:
    """
    Tokenize text into words with character offsets.
    
    Args:
        text: Text to tokenize
        skip_marker_tokens: If True, marker tokens are not included as words
    
    Returns:
        List of (charStart, charEnd, word) tuples
    """
    if not text:
        return []
    
    words = []
    # Match word sequences (letters, numbers, apostrophes within words)
    pattern = r"[\w']+|[^\s\w]+"
    
    for match in re.finditer(pattern, text, re.UNICODE):
        word = match.group()
        # Skip pure punctuation that's not meaningful
        if re.match(r"^[^\w]+$", word) and len(word) == 1 and word in ".,;:!?":
            continue
        
        # Skip marker token fragments if requested
        if skip_marker_tokens:
            # Check if this match is part of a marker token
            # Marker tokens look like: ⟦M:uuid⟧
            # The tokenizer will pick up the UUID part, so we check context
            start = match.start()
            end = match.end()
            
            # Check if we're inside a marker token
            # Look backwards for ⟦M: and forwards for ⟧
            is_in_marker = False
            
            # Find potential marker token boundary before this position
            search_start = max(0, start - 50)  # Look back up to 50 chars
            prefix = text[search_start:start]
            marker_start_pos = prefix.rfind('⟦M:')
            
            if marker_start_pos >= 0:
                # Found a marker start before us - check if we're inside it
                full_marker_start = search_start + marker_start_pos
                # Look for the closing bracket after us
                search_end = min(len(text), end + 50)
                suffix = text[end:search_end]
                marker_end_pos = suffix.find('⟧')
                
                if marker_end_pos >= 0:
                    # There's a closing bracket - we might be inside a marker
                    # Verify by checking if there's no closing bracket between marker start and us
                    between = text[full_marker_start:start]
                    if '⟧' not in between:
                        is_in_marker = True
            
            if is_in_marker:
                continue
        
        words.append((match.start(), match.end(), word))
    
    return words


def tokenize_words_with_markers(text: str) -> Tuple[List[Tuple[int, int, str]], List[Tuple[int, int, str]]]:
    """
    Tokenize text and separately extract marker token positions.
    
    Returns:
        Tuple of (word_list, marker_list)
        - word_list: List of (charStart, charEnd, word) for regular words
        - marker_list: List of (charStart, charEnd, marker_id) for marker tokens
    """
    words = tokenize_words(text, skip_marker_tokens=True)
    
    markers = []
    for match in MARKER_TOKEN_PATTERN.finditer(text):
        markers.append((match.start(), match.end(), match.group(1).lower()))
    
    return words, markers


def get_word_at_char_position(text: str, char_pos: int) -> Tuple[int, int, str]:
    """
    Find the word containing a specific character position.
    
    Returns:
        (charStart, charEnd, word) or None if not in a word
    """
    words = tokenize_words(text)
    for start, end, word in words:
        if start <= char_pos < end:
            return (start, end, word)
    return None


def find_word_index(text: str, char_start: int, char_end: int) -> int:
    """
    Find the word index for a character range.
    Useful for converting char offsets to word index.
    
    Returns:
        Word index (0-based) or -1 if not found
    """
    words = tokenize_words(text)
    for i, (start, end, word) in enumerate(words):
        if start == char_start and end == char_end:
            return i
        # Fuzzy match - if ranges overlap significantly
        if start <= char_start < end or start < char_end <= end:
            return i
    return -1


def align_word_timings(
    normalized_text: str,
    elevenlabs_alignment: dict
) -> List[dict]:
    """
    Convert ElevenLabs alignment data to our WordTiming format.
    
    ElevenLabs provides character-level timing. We aggregate to word level.
    
    Args:
        normalized_text: The normalized text that was sent to TTS
        elevenlabs_alignment: Response from ElevenLabs convert-with-timestamps
            Format: {
                "characters": ["H", "e", "l", "l", "o", ...],
                "character_start_times_seconds": [0.0, 0.1, ...],
                "character_end_times_seconds": [0.1, 0.2, ...]
            }
    
    Returns:
        List of WordTiming dicts: [{charStart, charEnd, startTime, endTime, word}]
    """
    if not elevenlabs_alignment:
        return []
    
    chars = elevenlabs_alignment.get("characters", [])
    start_times = elevenlabs_alignment.get("character_start_times_seconds", [])
    end_times = elevenlabs_alignment.get("character_end_times_seconds", [])
    
    if not chars or len(chars) != len(start_times) or len(chars) != len(end_times):
        return []
    
    # Reconstruct text from ElevenLabs characters to build position map
    elevenlabs_text = "".join(chars)
    
    # Build a mapping from ElevenLabs char index to timing
    # This accounts for any character differences between normalized and EL output
    
    # Get word positions from our normalized text
    words = tokenize_words(normalized_text)
    
    word_timings = []
    search_start = 0  # Track where to search from to handle duplicate words
    
    for char_start, char_end, word in words:
        word_start_time = None
        word_end_time = None
        
        # Try to find this word in ElevenLabs output, starting from last found position
        # This handles repeated words correctly by searching sequentially
        word_pos = elevenlabs_text.find(word, search_start)
        
        if word_pos >= 0:
            # Found the word - get timing from first and last character
            word_start_time = start_times[word_pos] if word_pos < len(start_times) else None
            word_end_pos = word_pos + len(word) - 1
            word_end_time = end_times[word_end_pos] if word_end_pos < len(end_times) else None
            
            # Move search position past this word for next iteration
            search_start = word_pos + len(word)
        else:
            # Word not found after search_start - try from beginning as fallback
            word_pos = elevenlabs_text.find(word)
            if word_pos >= 0:
                word_start_time = start_times[word_pos] if word_pos < len(start_times) else None
                word_end_pos = word_pos + len(word) - 1
                word_end_time = end_times[word_end_pos] if word_end_pos < len(end_times) else None
            else:
                # Word truly not found - try case-insensitive match
                lower_el_text = elevenlabs_text.lower()
                lower_word = word.lower()
                word_pos = lower_el_text.find(lower_word, 0)
                if word_pos >= 0:
                    word_start_time = start_times[word_pos] if word_pos < len(start_times) else None
                    word_end_pos = word_pos + len(lower_word) - 1
                    word_end_time = end_times[word_end_pos] if word_end_pos < len(end_times) else None
        
        if word_start_time is not None and word_end_time is not None:
            word_timings.append({
                "charStart": char_start,
                "charEnd": char_end,
                "startTime": word_start_time,
                "endTime": word_end_time,
                "word": word
            })
        elif word_start_time is not None:
            # Have start but not end - estimate end
            word_timings.append({
                "charStart": char_start,
                "charEnd": char_end,
                "startTime": word_start_time,
                "endTime": word_start_time + 0.1,  # Default 100ms duration
                "word": word
            })
    
    return word_timings


def estimate_word_timings(text: str, total_duration: float) -> List[dict]:
    """
    Estimate word timings based on character count when ElevenLabs alignment is unavailable.
    This is a fallback that distributes time proportionally.
    
    Args:
        text: Normalized text
        total_duration: Total audio duration in seconds
    
    Returns:
        List of WordTiming dicts with estimated times
    """
    words = tokenize_words(text)
    if not words or total_duration <= 0:
        return []
    
    # Calculate total character weight
    total_chars = sum(len(word) for _, _, word in words)
    if total_chars == 0:
        return []
    
    # Distribute time proportionally
    word_timings = []
    current_time = 0.0
    
    for char_start, char_end, word in words:
        word_duration = (len(word) / total_chars) * total_duration
        word_timings.append({
            "charStart": char_start,
            "charEnd": char_end,
            "startTime": current_time,
            "endTime": current_time + word_duration,
            "word": word
        })
        current_time += word_duration
    
    return word_timings

