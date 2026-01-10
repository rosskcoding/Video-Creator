from typing import Any, Optional
import subprocess
import os
import json
import logging

from llama_index.core.workflow import (
    step,
    Context,
    Workflow,
    Event,
    StartEvent,
    StopEvent,
)
from llama_index.core.workflow.retry_policy import ConstantDelayRetryPolicy

from models import PresentationStructure
from agents.narrator import narrate

logger = logging.getLogger(__name__)


class NarrationRequestReceived(Event):
    slide_index: int


class SlideNarrated(Event):
    slide_index: int


class SlideClipCreated(Event):
    slide_index: int
    clip_file: str


class VideoCreationError(Exception):
    """Custom exception for video creation errors"""
    pass


class PresenterVideoCreaterWorkflow(Workflow):
    def __init__(
        self,
        *args: Any,
        model: str,
        voice: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.model = model
        self.voice = voice

    @step
    async def start(
        self, ctx: Context, ev: StartEvent
    ) -> NarrationRequestReceived | StopEvent:
        presentation_dir = ev.presentation_dir
        await ctx.set("presentation_dir", presentation_dir)
        
        # Use JSON structure file only (safe, human-readable).
        structure_file = os.path.join(presentation_dir, "structure.json")

        if not os.path.exists(structure_file):
            return StopEvent(result="No structure.json found")

        with open(structure_file, "r", encoding="utf-8") as f:
            structure = PresentationStructure.model_validate_json(f.read())
        
        await ctx.set("structure", structure)
        slides = structure.slides
        num_slides = len(slides)
        await ctx.set("num_slides", num_slides)
        
        if num_slides == 0:
            return StopEvent(result="No slides in presentation")
        
        # Return the first event; enqueue the rest explicitly (avoid duplicate slide 0 work).
        for i in range(1, num_slides):
            ctx.send_event(NarrationRequestReceived(slide_index=i))
        return NarrationRequestReceived(slide_index=0)

    @step(num_workers=5, retry_policy=ConstantDelayRetryPolicy())
    async def narrate_slide(
        self, ctx: Context, ev: NarrationRequestReceived
    ) -> SlideNarrated:
        slide_index = ev.slide_index
        presentation_dir = await ctx.get("presentation_dir")
        slide_dir = os.path.join(presentation_dir, f"slide_{slide_index}")
        narration_file = os.path.join(slide_dir, "narration.txt")
        narration_audio_file = os.path.join(slide_dir, "narration.mp3")
        
        logger.info(f"Narrating slide_{slide_index}")
        
        if os.path.exists(narration_audio_file):
            return SlideNarrated(slide_index=slide_index)
        
        with open(narration_file, "r", encoding="utf-8") as f:
            narration = f.read()
        
        await narrate(narration, self.voice, self.model, narration_audio_file)
        return SlideNarrated(slide_index=slide_index)

    @step(num_workers=5, retry_policy=ConstantDelayRetryPolicy())
    async def create_slide_clip(
        self, ctx: Context, ev: SlideNarrated
    ) -> SlideClipCreated:
        slide_index = ev.slide_index
        presentation_dir = await ctx.get("presentation_dir")
        slide_dir = os.path.join(presentation_dir, f"slide_{slide_index}")
        slide_clip_file = os.path.join(slide_dir, "clip.mp4")
        
        logger.info(f"Creating clip for slide_{slide_index}")
        
        if os.path.exists(slide_clip_file):
            return SlideClipCreated(slide_index=slide_index, clip_file=slide_clip_file)
        
        slide_ss_file = os.path.join(
            presentation_dir, f"presentation_{slide_index+1}_1280x720.png"
        )
        slide_audio_file = os.path.join(slide_dir, "narration.mp3")
        
        # Get audio duration using ffprobe - use list args for safety
        duration = self._get_audio_duration(slide_audio_file)
        adjusted_duration = duration / 1.4 + 0.5
        
        # Create clip using ffmpeg - use list args for safety (no shell injection)
        self._create_video_clip(
            slide_ss_file, 
            slide_audio_file, 
            slide_clip_file, 
            adjusted_duration
        )
        
        # Verify output file exists and has content
        if not os.path.exists(slide_clip_file):
            raise VideoCreationError(f"Failed to create clip for slide {slide_index}")
        
        if os.path.getsize(slide_clip_file) == 0:
            os.remove(slide_clip_file)
            raise VideoCreationError(f"Created empty clip for slide {slide_index}")
        
        logger.info(f"Created clip for slide_{slide_index}")
        return SlideClipCreated(slide_index=slide_index, clip_file=slide_clip_file)

    def _get_audio_duration(self, audio_file: str) -> float:
        """Get audio duration using ffprobe with proper error handling."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_file,
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # We'll check manually for better error messages
        )
        
        if result.returncode != 0:
            raise VideoCreationError(
                f"ffprobe failed for {audio_file}: {result.stderr}"
            )
        
        if not result.stdout.strip():
            raise VideoCreationError(
                f"ffprobe returned empty output for {audio_file}"
            )
        
        try:
            output = json.loads(result.stdout)
            return float(output["format"]["duration"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise VideoCreationError(
                f"Failed to parse ffprobe output for {audio_file}: {e}"
            ) from e

    def _create_video_clip(
        self, 
        image_file: str, 
        audio_file: str, 
        output_file: str, 
        duration: float
    ) -> None:
        """Create video clip from image and audio using ffmpeg."""
        # Use list arguments to avoid shell injection and handle paths with spaces
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-loop", "1",
            "-i", image_file,
            "-i", audio_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-t", str(duration),
            "-vf", "format=yuv420p",
            "-filter:a", "atempo=1.4",
            output_file,
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode != 0:
            raise VideoCreationError(
                f"ffmpeg failed to create clip: {result.stderr}"
            )

    @step
    async def combine_clips(
        self, ctx: Context, ev: SlideClipCreated
    ) -> Optional[StopEvent]:
        num_slides = await ctx.get("num_slides")
        presentation_dir = await ctx.get("presentation_dir")
        
        events = ctx.collect_events(ev, [SlideClipCreated] * num_slides)
        if events is None:
            # Not all clips ready yet - this is expected behavior in LlamaIndex
            return None
        
        all_clips_file = os.path.join(presentation_dir, "clips.txt")
        clips = []
        for i in range(num_slides):
            clip_file = os.path.join(f"slide_{i}", "clip.mp4")
            clips.append(f"file '{clip_file}'")
        
        with open(all_clips_file, "w", encoding="utf-8") as f:
            f.write("\n".join(clips))
        
        presentation_video_file = os.path.join(presentation_dir, "presentation.mp4")
        
        logger.info("Rendering full presentation video...")
        
        # Use list arguments for subprocess
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", all_clips_file,
            "-c", "copy",
            presentation_video_file,
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=presentation_dir,  # Run in presentation dir for relative paths
        )
        
        if result.returncode != 0:
            raise VideoCreationError(
                f"ffmpeg failed to combine clips: {result.stderr}"
            )
        
        # Verify output
        if not os.path.exists(presentation_video_file):
            raise VideoCreationError("Failed to create final presentation video")
        
        if os.path.getsize(presentation_video_file) == 0:
            os.remove(presentation_video_file)
            raise VideoCreationError("Created empty presentation video")
        
        logger.info(f'Presentation video created: "{presentation_video_file}"')
        return StopEvent(result=f"Presentation video created: {presentation_video_file}")
