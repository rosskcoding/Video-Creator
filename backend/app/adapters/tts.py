"""
ElevenLabs TTS Adapter
Based on rsrohan99/presenter but with caching and error handling
"""
import hashlib
import tempfile
import asyncio
from pathlib import Path
from typing import Optional

from elevenlabs.client import ElevenLabs

from app.core.config import settings

# HARDCODED VOICE - always use this voice, ignore any other settings
HARDCODED_VOICE_ID = "iBcRJa9DRdlJlVihC0V6"


class TTSAdapter:
    """Adapter for ElevenLabs Text-to-Speech"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,  # IGNORED - using hardcoded voice
        model: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ):
        self.api_key = api_key or settings.ELEVENLABS_API_KEY
        self.voice_id = HARDCODED_VOICE_ID  # ALWAYS use hardcoded voice
        self.model = model or settings.DEFAULT_TTS_MODEL
        self.timeout_sec = timeout_sec or settings.TTS_HTTP_TIMEOUT_SEC
        
        # Configure client with timeout
        self.client = ElevenLabs(
            api_key=self.api_key,
            timeout=self.timeout_sec,
        )
    
    @staticmethod
    def compute_audio_hash(
        text: str,
        voice_id: str,  # IGNORED - using hardcoded voice
        lang: str,
        model: str = "eleven_flash_v2_5",
        params_version: str = "v1"
    ) -> str:
        """
        Compute cache key for TTS audio.
        Hash = sha256(lang + voice_id + text + model + params_version)
        """
        # ALWAYS use hardcoded voice for hash
        content = f"{lang}|{HARDCODED_VOICE_ID}|{text}|{model}|{params_version}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def generate_speech(
        self,
        text: str,
        output_path: Path,
        voice_id: Optional[str] = None,  # IGNORED - using hardcoded voice
        model: Optional[str] = None,
    ) -> float:
        """
        Generate speech from text and save to file.
        
        Args:
            text: Text to convert to speech
            output_path: Path to save the audio file (WAV preferred)
            voice_id: IGNORED - always uses hardcoded voice
            model: TTS model ID
            
        Returns:
            Duration of generated audio in seconds
        """
        # ALWAYS use hardcoded voice, ignore parameter
        voice_id = HARDCODED_VOICE_ID
        model = model or self.model
        
        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # ElevenLabs SDK streams audio bytes (typically mp3 by default).
        # If caller requests .wav, we download mp3 into a temp file and transcode to WAV.
        wants_wav = output_path.suffix.lower() == ".wav"
        tmp_suffix = ".mp3"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_audio_path = Path(tmp_dir) / f"tts{tmp_suffix}"

            # Generate audio (keep this call minimal to avoid SDK incompatibilities)
            response = self.client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=model,
            )

            with open(tmp_audio_path, "wb") as f:
                for chunk in response:
                    if chunk:
                        f.write(chunk)

            if wants_wav:
                await self._transcode_to_wav(tmp_audio_path, output_path)
            else:
                # Save as-is (mp3)
                output_path.write_bytes(tmp_audio_path.read_bytes())
        
        # Get duration using ffprobe
        duration = await self._get_audio_duration(output_path)
        return duration
    
    async def _transcode_to_wav(self, input_path: Path, output_path: Path) -> None:
        """Transcode audio to WAV (PCM) for stable mixing."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg transcode error: {stderr.decode()}")

    async def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe with proper error handling"""
        import json
        
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(audio_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        # Check return code first
        if process.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            raise RuntimeError(
                f"ffprobe failed for {audio_path}: exit code {process.returncode}, error: {error_msg}"
            )
        
        # Check for empty output
        if not stdout or not stdout.strip():
            raise RuntimeError(
                f"ffprobe returned empty output for {audio_path}"
            )
        
        # Parse JSON with error handling
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"ffprobe returned invalid JSON for {audio_path}: {e}. "
                f"Output: {stdout.decode()[:200]}"
            )
        
        # Validate structure
        if "format" not in result or "duration" not in result.get("format", {}):
            raise RuntimeError(
                f"ffprobe output missing duration for {audio_path}. "
                f"Result: {result}"
            )
        
        return float(result["format"]["duration"])
    
    def check_cache(self, audio_hash: str, audio_dir: Path) -> Optional[Path]:
        """
        Check if audio with given hash exists in cache.
        Returns path to cached file or None.
        """
        # Look for any file matching the hash pattern
        for file in audio_dir.glob(f"*_{audio_hash}.*"):
            if file.exists():
                return file
        return None


# Singleton instance
tts_adapter = TTSAdapter()

