import os
import asyncio
from functools import partial
from typing import Iterator

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

# Load environment once at module import, not per call
load_dotenv()

# Initialize client once (lazy singleton pattern)
_client: ElevenLabs | None = None


def _get_client() -> ElevenLabs:
    """Get or create ElevenLabs client singleton."""
    global _client
    if _client is None:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable not set")
        _client = ElevenLabs(api_key=api_key)
    return _client


def _narrate_sync(text: str, voice: str, model: str, output_file: str) -> None:
    """Synchronous narration implementation."""
    client = _get_client()
    response: Iterator[bytes] = client.text_to_speech.convert(
        text=text, 
        voice_id=voice, 
        model_id=model
    )
    
    with open(output_file, "wb") as f:
        for chunk in response:
            if chunk:
                f.write(chunk)
    
    # Verify file was created with content
    if not os.path.exists(output_file):
        raise RuntimeError(f"Failed to create narration file: {output_file}")
    
    if os.path.getsize(output_file) == 0:
        os.remove(output_file)
        raise RuntimeError(f"Created empty narration file: {output_file}")


async def narrate(text: str, voice: str, model: str, output_file: str) -> None:
    """
    Generate narration audio from text using ElevenLabs TTS.
    
    This function is async-safe - it runs the synchronous ElevenLabs client
    in a thread pool to avoid blocking the event loop.
    
    Args:
        text: The text to narrate
        voice: ElevenLabs voice ID
        model: ElevenLabs model ID
        output_file: Path to save the audio file
    
    Raises:
        ValueError: If ELEVENLABS_API_KEY is not set
        RuntimeError: If narration fails or creates empty file
    """
    # Run sync I/O in thread pool to not block event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,  # Use default executor (ThreadPoolExecutor)
        partial(_narrate_sync, text, voice, model, output_file)
    )
