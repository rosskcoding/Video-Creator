"""
FFmpeg Video Render Adapter
Based on rsrohan99/presenter but with configurable timing and audio mix
"""
import asyncio
import json
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.config import settings


class RenderAdapter:
    """Adapter for FFmpeg video rendering with audio mix"""
    
    def __init__(self):
        self.width = settings.VIDEO_WIDTH
        self.height = settings.VIDEO_HEIGHT
        self.fps = settings.VIDEO_FPS
        self.video_codec = settings.VIDEO_CODEC
        self.audio_codec = settings.AUDIO_CODEC
        self.audio_bitrate = settings.AUDIO_BITRATE
        self.transition_type = settings.TRANSITION_TYPE
        self.transition_duration = settings.TRANSITION_DURATION_SEC
    
    async def render_video_from_slides(
        self,
        slides: List[Tuple[Path, float]],  # [(image_path, duration_sec), ...]
        audio_path: Path,
        output_path: Path,
        transition_type: Optional[str] = None,
        transition_duration: Optional[float] = None,
        job_id: Optional[str] = None,
    ) -> Path:
        """
        Render video from slide images with audio.
        
        Args:
            slides: List of (image_path, duration_sec) tuples
            audio_path: Path to final mixed audio
            output_path: Path for output MP4
            transition_type: 'fade', 'crossfade', or 'none'
            transition_duration: Duration of transition in seconds
            
        Returns:
            Path to rendered video
        """
        transition_type = (transition_type or self.transition_type or "fade").lower()
        transition_duration = float(transition_duration or self.transition_duration)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use job-specific temp directory to avoid race conditions
        # when multiple renders run in parallel
        job_suffix = f"_{job_id}" if job_id else ""
        temp_dir = output_path.parent / f"_tmp{job_suffix}"
        temp_dir.mkdir(exist_ok=True)
        
        # Create individual clip files in job-specific temp dir
        clips_dir = temp_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        
        clip_paths = []
        original_durations = [d for _, d in slides]
        num_slides = len(slides)

        for i, (image_path, duration) in enumerate(slides):
            clip_path = clips_dir / f"clip_{i:03d}.mp4"
            clip_duration = duration

            fade_in = False
            fade_out = False
            if transition_type == "fade":
                # Fade-to-black between clips (no overlap) keeps total duration == sum(slide durations)
                fade_in = i != 0
                fade_out = i != (num_slides - 1)
            elif transition_type == "crossfade":
                # Crossfade overlaps clips by transition_duration, so we extend each clip after the first
                # to keep total duration aligned with the audio timeline.
                if i > 0:
                    clip_duration = duration + transition_duration

            await self._create_image_clip(
                image_path=image_path,
                duration=clip_duration,
                output_path=clip_path,
                fade_in=fade_in,
                fade_out=fade_out,
                fade_duration=transition_duration,
            )
            clip_paths.append(clip_path)
        
        silent_video = temp_dir / "silent.mp4"
        if transition_type == "crossfade" and len(clip_paths) > 1:
            await self._crossfade_clips(
                clip_paths=clip_paths,
                slide_durations=original_durations,
                transition_duration=transition_duration,
                output_path=silent_video,
            )
        else:
            # Concat clips (fast path)
            concat_file = temp_dir / "concat.txt"
            with open(concat_file, "w") as f:
                for clip_path in clip_paths:
                    f.write(f"file '{clip_path.absolute()}'\n")
            await self._concat_clips(concat_file, silent_video)
        
        # Add audio
        await self._add_audio_to_video(silent_video, audio_path, output_path)
        
        # Clean up temp directory after successful render
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass  # Ignore cleanup errors
        
        return output_path
    
    async def _create_image_clip(
        self,
        image_path: Path,
        duration: float,
        output_path: Path,
        fade_in: bool = False,
        fade_out: bool = False,
        fade_duration: float = 0.5,
    ) -> None:
        """Create video clip from single image"""
        vf = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,"
            f"format=yuv420p"
        )
        if fade_in and duration > 0 and fade_duration > 0:
            vf += f",fade=t=in:st=0:d={fade_duration}"
        if fade_out and duration > fade_duration and fade_duration > 0:
            vf += f",fade=t=out:st={max(duration - fade_duration, 0)}:d={fade_duration}"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-c:v", self.video_codec,
            "-t", str(duration),
            "-vf", vf,
            "-r", str(self.fps),
            "-pix_fmt", "yuv420p",
            str(output_path)
        ]
        
        await self._run_ffmpeg(cmd)
    
    async def _concat_clips(
        self,
        concat_file: Path,
        output_path: Path,
    ) -> None:
        """Concatenate pre-rendered video clips (no overlap)."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        
        await self._run_ffmpeg(cmd)

    async def _crossfade_clips(
        self,
        clip_paths: List[Path],
        slide_durations: List[float],
        transition_duration: float,
        output_path: Path,
    ) -> None:
        """Crossfade clips using xfade while keeping total duration aligned to slide_durations."""
        if not clip_paths:
            raise ValueError("No clips to crossfade")

        if len(clip_paths) == 1:
            # Just copy the single clip
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(clip_paths[0]),
                "-c",
                "copy",
                str(output_path),
            ]
            await self._run_ffmpeg(cmd)
            return

        inputs: List[str] = []
        for p in clip_paths:
            inputs.extend(["-i", str(p)])

        # Build filter_complex
        # Normalize PTS
        filters: List[str] = []
        for i in range(len(clip_paths)):
            filters.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

        # Sequential xfade
        current_label = "v0"
        cumulative = 0.0
        for i in range(len(clip_paths) - 1):
            cumulative += slide_durations[i]
            offset = max(cumulative - transition_duration, 0.0)
            next_label = f"v{i+1}"
            out_label = f"vxf{i}"
            filters.append(
                f"[{current_label}][{next_label}]xfade=transition=fade:duration={transition_duration}:offset={offset}[{out_label}]"
            )
            current_label = out_label

        filter_complex = ";".join(filters)

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            f"[{current_label}]",
            "-c:v",
            self.video_codec,
            "-r",
            str(self.fps),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        await self._run_ffmpeg(cmd)
    
    async def _add_audio_to_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path
    ) -> None:
        """Combine video with audio track"""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", self.audio_codec,
            "-b:a", self.audio_bitrate,
            "-shortest",
            str(output_path)
        ]
        
        await self._run_ffmpeg(cmd)
    
    async def mix_audio(
        self,
        voice_path: Path,
        music_path: Optional[Path],
        output_path: Path,
        voice_gain_db: float = 0.0,
        music_gain_db: float = -22.0,
        ducking_enabled: bool = True,
        ducking_strength: str = "default",
        target_lufs: int = -14,
    ) -> Path:
        """
        Mix voice and background music with ducking and loudness normalization.
        
        Args:
            voice_path: Path to voice timeline WAV
            music_path: Path to music file (or None for no music)
            output_path: Path for output mixed audio
            voice_gain_db: Voice gain adjustment in dB
            music_gain_db: Music gain adjustment in dB
            ducking_enabled: Whether to duck music under voice
            ducking_strength: 'light', 'default', or 'strong'
            target_lufs: Target loudness in LUFS
            
        Returns:
            Path to mixed audio
            
        Raises:
            ValueError: If voice file is empty or corrupted
        """
        import logging
        logger = logging.getLogger(__name__)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Validate voice file exists
        if not Path(voice_path).exists():
            raise ValueError(f"Voice file not found: {voice_path}")
        
        # Check voice file size (empty file = corrupted/missing)
        voice_size = Path(voice_path).stat().st_size
        if voice_size < 100:  # WAV header is ~44 bytes minimum
            raise ValueError(f"Voice file appears empty or corrupted: {voice_path}")
        
        # Get voice duration and validate
        try:
            voice_duration = await self._get_audio_duration(voice_path)
        except Exception as e:
            raise ValueError(f"Failed to read voice file duration: {voice_path}. Error: {e}")
        
        if voice_duration <= 0:
            raise ValueError(f"Voice file has zero or negative duration: {voice_path}")
        
        # Check if we should use music
        use_music = False
        if music_path is not None and Path(music_path).exists():
            # Validate music file is readable
            try:
                music_duration = await self._get_audio_duration(music_path)
                if music_duration > 0:
                    use_music = True
                else:
                    logger.warning(f"Music file has zero duration, skipping: {music_path}")
            except Exception as e:
                logger.warning(f"Failed to read music file, proceeding without music: {music_path}. Error: {e}")
        
        if not use_music:
            # Just normalize voice (no music or music is broken)
            await self._normalize_audio(voice_path, output_path, voice_gain_db, target_lufs)
            return output_path
        
        # Build filter complex for mixing
        ducking_params = self._get_ducking_params(ducking_strength)
        
        if ducking_enabled:
            # Sidechain compress music with voice
            filter_complex = (
                f"[0:a]volume={voice_gain_db}dB[voice];"
                f"[1:a]atrim=0:{voice_duration},asetpts=PTS-STARTPTS,volume={music_gain_db}dB[music_vol];"
                f"[music_vol][voice]sidechaincompress="
                f"threshold={ducking_params['threshold']}:"
                f"ratio={ducking_params['ratio']}:"
                f"attack={ducking_params['attack']}:"
                f"release={ducking_params['release']}[music_ducked];"
                # NOTE: amix has normalize=true by default, which makes music much quieter.
                # We control levels via voice_gain_db/music_gain_db, so disable normalization.
                f"[voice][music_ducked]amix=inputs=2:duration=first:normalize=0[mixed];"
                f"[mixed]loudnorm=I={target_lufs}:TP=-1.5:LRA=11[out]"
            )
        else:
            # Simple mix without ducking
            filter_complex = (
                f"[0:a]volume={voice_gain_db}dB[voice];"
                f"[1:a]atrim=0:{voice_duration},asetpts=PTS-STARTPTS,volume={music_gain_db}dB[music];"
                # NOTE: See comment above about amix normalization.
                f"[voice][music]amix=inputs=2:duration=first:normalize=0[mixed];"
                f"[mixed]loudnorm=I={target_lufs}:TP=-1.5:LRA=11[out]"
            )
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-stream_loop", "-1",
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "pcm_s16le",  # WAV output
            str(output_path)
        ]
        
        try:
            await self._run_ffmpeg(cmd)
        except RuntimeError as e:
            # If mixing fails due to music issues, fallback to voice only
            if "music" in str(e).lower() or "stream 1" in str(e).lower():
                logger.warning(f"Audio mixing failed, falling back to voice only: {e}")
                await self._normalize_audio(voice_path, output_path, voice_gain_db, target_lufs)
            else:
                raise
        
        return output_path
    
    async def build_voice_timeline(
        self,
        audio_files: List[Tuple[Optional[Path], float, float]],  # [(path_or_none, pre_pad, post_pad), ...]
        output_path: Path,
    ) -> Path:
        """
        Build voice timeline by concatenating audio files with padding.
        Supports None path for silent segments (slides without audio).
        
        Args:
            audio_files: List of (audio_path_or_none, pre_padding_sec, post_padding_sec)
                        If path is None, creates silence for (pre_pad + post_pad) duration
            output_path: Path for output timeline WAV
            
        Returns:
            Path to timeline audio
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build filter for padding and concatenation
        inputs = []
        filter_parts = []
        input_idx = 0
        segment_labels = []
        
        for i, (audio_path, pre_pad, post_pad) in enumerate(audio_files):
            if audio_path is not None:
                # Real audio file with padding
                inputs.extend(["-i", str(audio_path)])
                filter_parts.append(
                    f"[{input_idx}:a]adelay={int(pre_pad * 1000)}|{int(pre_pad * 1000)},"
                    f"apad=pad_dur={post_pad}[a{i}]"
                )
                input_idx += 1
            else:
                # Silent segment (slide without audio)
                # Generate silence using anullsrc
                silence_duration = pre_pad + post_pad  # pre_pad=0, post_pad=duration for silent slides
                filter_parts.append(
                    f"anullsrc=r=44100:cl=stereo,atrim=0:{silence_duration}[a{i}]"
                )
            segment_labels.append(f"[a{i}]")
        
        # Concat all segments
        concat_inputs = "".join(segment_labels)
        filter_parts.append(f"{concat_inputs}concat=n={len(audio_files)}:v=0:a=1[out]")
        
        filter_complex = ";".join(filter_parts)
        
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            str(output_path)
        ]
        
        await self._run_ffmpeg(cmd)
        return output_path
    
    async def generate_srt(
        self,
        subtitles: List[Tuple[float, float, str]],  # [(start_sec, end_sec, text), ...]
        output_path: Path,
    ) -> Path:
        """
        Generate SRT subtitle file.
        
        Args:
            subtitles: List of (start_time, end_time, text)
            output_path: Path for output SRT file
            
        Returns:
            Path to SRT file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds - int(seconds)) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
        with open(output_path, "w", encoding="utf-8") as f:
            for i, (start, end, text) in enumerate(subtitles, 1):
                f.write(f"{i}\n")
                f.write(f"{format_time(start)} --> {format_time(end)}\n")
                f.write(f"{text}\n\n")
        
        return output_path
    
    def _get_ducking_params(self, strength: str) -> dict:
        """Get sidechain compressor parameters based on strength"""
        params = {
            "light": {
                "threshold": "0.03",
                "ratio": "3",
                "attack": "100",
                "release": "500",
            },
            "default": {
                "threshold": "0.02",
                "ratio": "6",
                "attack": "50",
                "release": "400",
            },
            "strong": {
                "threshold": "0.01",
                "ratio": "10",
                "attack": "20",
                "release": "300",
            },
        }
        return params.get(strength, params["default"])
    
    async def _normalize_audio(
        self,
        input_path: Path,
        output_path: Path,
        gain_db: float,
        target_lufs: int
    ) -> None:
        """Normalize audio to target loudness"""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-af", f"volume={gain_db}dB,loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le",
            str(output_path)
        ]
        await self._run_ffmpeg(cmd)
    
    async def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe with proper error handling"""
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
    
    async def _run_ffmpeg(self, cmd: List[str]) -> Tuple[str, str]:
        """Run FFmpeg command and capture output"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode()}")
        
        return stdout.decode(), stderr.decode()


# Singleton instance
render_adapter = RenderAdapter()

