"""
Marker Token Utilities for EPIC A: Stable Multi-language Triggers

Marker tokens are special identifiers embedded in script text that:
1. Are preserved during translation (not translated)
2. Allow deterministic marker position lookup across languages
3. Enable stable animation trigger timing

Token format: ⟦M:<uuid>⟧
Example: ⟦M:6f2c9f7a-1234-5678-9abc-def012345678⟧

The tokens use Unicode brackets (⟦ and ⟧) to avoid conflicts with
common text characters and make them visually distinct.
"""
import re
import uuid
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

# Marker token pattern: ⟦M:uuid⟧
# UUID format: 8-4-4-4-12 hex characters with dashes
MARKER_TOKEN_PATTERN = re.compile(
    r'⟦M:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})⟧',
    re.IGNORECASE
)

# Opening and closing brackets for marker tokens
MARKER_OPEN = '⟦M:'
MARKER_CLOSE = '⟧'


@dataclass
class MarkerTokenInfo:
    """Information about a marker token found in text"""
    marker_id: str      # UUID of the marker
    start: int          # Start position in text (inclusive)
    end: int            # End position in text (exclusive)
    token: str          # Full token string


def format_marker_token(marker_id: str) -> str:
    """
    Format a marker ID as a marker token.
    
    Args:
        marker_id: UUID string of the marker
        
    Returns:
        Formatted marker token string: ⟦M:uuid⟧
    """
    return f'{MARKER_OPEN}{marker_id}{MARKER_CLOSE}'


def parse_marker_tokens(text: str) -> List[MarkerTokenInfo]:
    """
    Parse all marker tokens from text.
    
    Args:
        text: Text to search for marker tokens
        
    Returns:
        List of MarkerTokenInfo for each token found, in order of appearance
    """
    tokens = []
    for match in MARKER_TOKEN_PATTERN.finditer(text):
        tokens.append(MarkerTokenInfo(
            marker_id=match.group(1).lower(),  # Normalize UUID to lowercase
            start=match.start(),
            end=match.end(),
            token=match.group(0)
        ))
    return tokens


def contains_marker_tokens(text: str) -> bool:
    """Check if text contains any marker tokens."""
    return bool(MARKER_TOKEN_PATTERN.search(text))


def extract_marker_ids(text: str) -> List[str]:
    """
    Extract all marker IDs from text.
    
    Args:
        text: Text containing marker tokens
        
    Returns:
        List of marker UUIDs (lowercase)
    """
    return [t.marker_id for t in parse_marker_tokens(text)]


def strip_marker_tokens(text: str) -> str:
    """
    Remove all marker tokens from text.
    
    This is useful for display purposes when tokens should be hidden.
    
    Args:
        text: Text with marker tokens
        
    Returns:
        Text with all marker tokens removed
    """
    return MARKER_TOKEN_PATTERN.sub('', text)


def insert_marker_token_at_position(
    text: str,
    marker_id: str,
    position: int
) -> str:
    """
    Insert a marker token at a specific position in text.
    
    Args:
        text: Original text
        marker_id: UUID of the marker
        position: Character position to insert at
        
    Returns:
        Text with marker token inserted
    """
    token = format_marker_token(marker_id)
    return text[:position] + token + text[position:]


def insert_marker_token_before_word(
    text: str,
    marker_id: str,
    word_start: int,
    word_end: int
) -> Tuple[str, int, int]:
    """
    Insert a marker token immediately before a word.
    
    Args:
        text: Original text
        marker_id: UUID of the marker
        word_start: Start position of the word
        word_end: End position of the word
        
    Returns:
        Tuple of (new_text, new_word_start, new_word_end)
        The word positions are updated to account for the inserted token
    """
    token = format_marker_token(marker_id)
    new_text = text[:word_start] + token + text[word_start:]
    token_len = len(token)
    return new_text, word_start + token_len, word_end + token_len


def get_marker_position_in_text(
    text: str,
    marker_id: str
) -> Optional[Tuple[int, int]]:
    """
    Find the position of a specific marker token in text.
    
    Args:
        text: Text containing marker tokens
        marker_id: UUID of the marker to find
        
    Returns:
        Tuple of (start, end) positions, or None if not found
    """
    marker_id_lower = marker_id.lower()
    for token_info in parse_marker_tokens(text):
        if token_info.marker_id == marker_id_lower:
            return token_info.start, token_info.end
    return None


def find_anchor_word_for_marker(
    text: str,
    marker_id: str,
    word_positions: List[Tuple[int, int, str]]
) -> Optional[Tuple[int, int, str, float]]:
    """
    Find the anchor word for a marker (used to compute time_seconds).
    
    The anchor word is determined as:
    1. First word whose start position >= marker token end (word to the right)
    2. If no word to the right, use the last word before the marker
    
    Args:
        text: Text containing marker tokens
        marker_id: UUID of the marker
        word_positions: List of (char_start, char_end, word) tuples
        
    Returns:
        Tuple of (char_start, char_end, word, time_offset) or None
        time_offset is 0.0 for right-adjacent words, small positive for interpolation
    """
    marker_pos = get_marker_position_in_text(text, marker_id)
    if marker_pos is None:
        return None
    
    marker_start, marker_end = marker_pos
    
    # Find word to the right (first word starting at or after marker end)
    for char_start, char_end, word in word_positions:
        if char_start >= marker_end:
            return char_start, char_end, word, 0.0
    
    # No word to the right - find last word before marker
    last_word_before = None
    for char_start, char_end, word in word_positions:
        if char_end <= marker_start:
            last_word_before = (char_start, char_end, word)
    
    if last_word_before:
        return (*last_word_before, 0.0)
    
    return None


def compute_marker_time_from_word_timings(
    text: str,
    marker_id: str,
    word_timings: List[Dict]
) -> Optional[float]:
    """
    Compute the time_seconds for a marker based on word timings.
    
    Algorithm:
    1. Find the marker token position in text
    2. Find the anchor word (first word to the right of marker, or last word before)
    3. Return the startTime of that word
    
    Args:
        text: Text containing marker tokens
        marker_id: UUID of the marker
        word_timings: List of dicts with {charStart, charEnd, startTime, endTime, word}
        
    Returns:
        time_seconds value for the marker, or None if cannot be computed
    """
    marker_pos = get_marker_position_in_text(text, marker_id)
    if marker_pos is None:
        return None
    
    marker_start, marker_end = marker_pos
    
    # Sort timings by charStart to ensure order
    sorted_timings = sorted(word_timings, key=lambda t: t.get('charStart', 0))
    
    # Find first word starting at or after marker end (word to the right)
    for timing in sorted_timings:
        char_start = timing.get('charStart')
        if char_start is not None and char_start >= marker_end:
            return timing.get('startTime')
    
    # No word to the right - find last word before marker
    last_timing_before = None
    for timing in sorted_timings:
        char_end = timing.get('charEnd')
        if char_end is not None and char_end <= marker_start:
            last_timing_before = timing
    
    if last_timing_before:
        # Use endTime of last word before marker as approximate time
        return last_timing_before.get('endTime') or last_timing_before.get('startTime')
    
    return None


def build_text_with_markers(
    base_text: str,
    marker_insertions: List[Tuple[str, int]]
) -> str:
    """
    Insert multiple marker tokens into text at specified positions.
    
    The insertions are processed in reverse order to avoid position shifts.
    
    Args:
        base_text: Original text without markers
        marker_insertions: List of (marker_id, position) tuples
        
    Returns:
        Text with all marker tokens inserted
    """
    # Sort by position descending so we can insert without shifting issues
    sorted_insertions = sorted(marker_insertions, key=lambda x: x[1], reverse=True)
    
    result = base_text
    for marker_id, position in sorted_insertions:
        token = format_marker_token(marker_id)
        result = result[:position] + token + result[position:]
    
    return result


def normalize_text_preserving_tokens(
    text: str,
    normalize_fn
) -> str:
    """
    Apply text normalization while preserving marker tokens.
    
    This function:
    1. Extracts all marker tokens and their positions
    2. Replaces tokens with placeholders
    3. Applies normalization to the text
    4. Re-inserts the tokens at the appropriate positions
    
    Args:
        text: Text with marker tokens
        normalize_fn: Normalization function to apply (takes text, returns text)
        
    Returns:
        Normalized text with marker tokens preserved
    """
    tokens = parse_marker_tokens(text)
    
    if not tokens:
        # No tokens, just normalize
        return normalize_fn(text)
    
    # Replace tokens with unique placeholders that won't be affected by normalization
    # Use NULL character sequences that are unlikely to appear in text
    placeholder_template = '\x00MARKER{}\x00'
    
    # Replace tokens with placeholders (reverse order to maintain positions)
    modified_text = text
    placeholders = []
    for i, token_info in enumerate(reversed(tokens)):
        placeholder = placeholder_template.format(len(tokens) - 1 - i)
        placeholders.insert(0, (placeholder, token_info.token))
        modified_text = modified_text[:token_info.start] + placeholder + modified_text[token_info.end:]
    
    # Apply normalization
    normalized = normalize_fn(modified_text)
    
    # Replace placeholders back with original tokens
    for placeholder, original_token in placeholders:
        normalized = normalized.replace(placeholder, original_token)
    
    return normalized


def get_translation_prompt_instructions() -> str:
    """
    Get instructions for LLM translation to preserve marker tokens.
    
    Returns:
        Instruction text to include in translation prompts
    """
    return """CRITICAL: PRESERVE MARKER TOKENS
The text contains special marker tokens in the format ⟦M:uuid⟧ (e.g., ⟦M:6f2c9f7a-1234-5678-9abc-def012345678⟧).
These tokens MUST be:
1. NOT translated or modified in any way
2. Kept in the same relative position in the translated text (near the same word/concept)
3. Preserved exactly as they appear, including the brackets ⟦ and ⟧

Example:
Source: "The ⟦M:abc123⟧company reported strong results."
Translation (German): "Das ⟦M:abc123⟧Unternehmen meldete starke Ergebnisse."

The marker token stays next to the translated equivalent of "company" (Unternehmen)."""

