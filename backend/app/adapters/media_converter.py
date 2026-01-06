"""
Universal Media Converter
Supports PPTX, PDF, and images (JPEG, PNG, WEBP)
"""
import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from PIL import Image

from app.adapters.pptx_converter import pptx_converter


class MediaType(Enum):
    PPTX = "pptx"
    PDF = "pdf"
    IMAGE = "image"


@dataclass
class AspectRatio:
    name: str
    ratio: float  # width / height
    tolerance: float = 0.02  # 2% tolerance
    
    def matches(self, width: int, height: int) -> bool:
        actual_ratio = width / height
        return abs(actual_ratio - self.ratio) <= self.tolerance


# Standard aspect ratios for video/presentations
ALLOWED_ASPECT_RATIOS = [
    AspectRatio("16:9", 16/9),      # Landscape HD (1920x1080, 1280x720)
    AspectRatio("4:3", 4/3),        # Classic presentation (1024x768)
    AspectRatio("9:16", 9/16),      # Vertical video (Stories, Reels, TikTok)
    AspectRatio("1:1", 1/1),        # Square (Instagram)
]

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    '.pptx': MediaType.PPTX,
    '.ppt': MediaType.PPTX,
    '.pdf': MediaType.PDF,
    '.jpg': MediaType.IMAGE,
    '.jpeg': MediaType.IMAGE,
    '.png': MediaType.IMAGE,
    '.webp': MediaType.IMAGE,
}


class AspectRatioError(Exception):
    """Raised when file has unsupported aspect ratio"""
    def __init__(self, width: int, height: int, detected_ratio: float):
        self.width = width
        self.height = height
        self.detected_ratio = detected_ratio
        allowed = ", ".join(ar.name for ar in ALLOWED_ASPECT_RATIOS)
        super().__init__(
            f"Unsupported aspect ratio {width}x{height} ({detected_ratio:.2f}). "
            f"Allowed ratios: {allowed}"
        )


class UnsupportedFormatError(Exception):
    """Raised when file format is not supported"""
    pass


class MediaConverter:
    """Universal converter for PPTX, PDF, and images"""
    
    def __init__(self, dpi: int = 150):
        self.dpi = dpi
    
    @staticmethod
    def get_media_type(file_path: Path) -> MediaType:
        """Detect media type from file extension"""
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(SUPPORTED_EXTENSIONS.keys())
            raise UnsupportedFormatError(
                f"Unsupported format: {suffix}. Allowed: {allowed}"
            )
        return SUPPORTED_EXTENSIONS[suffix]
    
    @staticmethod
    def validate_aspect_ratio(width: int, height: int) -> AspectRatio:
        """
        Validate that dimensions match one of the allowed aspect ratios.
        Returns the matching AspectRatio or raises AspectRatioError.
        """
        for ar in ALLOWED_ASPECT_RATIOS:
            if ar.matches(width, height):
                return ar
        
        detected_ratio = width / height
        raise AspectRatioError(width, height, detected_ratio)
    
    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        validate_ratio: bool = True,
    ) -> Tuple[List[Path], Optional[str]]:
        """
        Convert any supported file to PNG slides.
        
        Args:
            input_path: Path to input file (PPTX, PDF, or image)
            output_dir: Directory for output PNG files
            validate_ratio: Whether to validate aspect ratio
            
        Returns:
            Tuple of (list of PNG paths, detected aspect ratio name or None)
            
        Raises:
            AspectRatioError: If aspect ratio validation fails
            UnsupportedFormatError: If file format not supported
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        media_type = self.get_media_type(input_path)
        
        if media_type == MediaType.PPTX:
            return await self._convert_pptx(input_path, output_dir, validate_ratio)
        elif media_type == MediaType.PDF:
            return await self._convert_pdf(input_path, output_dir, validate_ratio)
        elif media_type == MediaType.IMAGE:
            return await self._convert_image(input_path, output_dir, validate_ratio)
    
    async def _convert_pptx(
        self, 
        pptx_path: Path, 
        output_dir: Path,
        validate_ratio: bool,
    ) -> Tuple[List[Path], Optional[str]]:
        """Convert PPTX using existing converter"""
        # Use existing pptx_converter
        png_paths = await pptx_converter.convert_to_png(pptx_path, output_dir)
        
        # Validate first slide's aspect ratio if requested
        aspect_name = None
        if png_paths and validate_ratio:
            with Image.open(png_paths[0]) as img:
                ar = self.validate_aspect_ratio(img.width, img.height)
                aspect_name = ar.name
        
        return png_paths, aspect_name
    
    async def _convert_pdf(
        self,
        pdf_path: Path,
        output_dir: Path,
        validate_ratio: bool,
    ) -> Tuple[List[Path], Optional[str]]:
        """Convert PDF directly to PNG (skip LibreOffice step)"""
        # Use pdftoppm or ImageMagick
        png_paths = await self._pdf_to_png(pdf_path, output_dir)
        
        # Validate first page's aspect ratio
        aspect_name = None
        if png_paths and validate_ratio:
            with Image.open(png_paths[0]) as img:
                ar = self.validate_aspect_ratio(img.width, img.height)
                aspect_name = ar.name
        
        return png_paths, aspect_name
    
    async def _convert_image(
        self,
        image_path: Path,
        output_dir: Path,
        validate_ratio: bool,
    ) -> Tuple[List[Path], Optional[str]]:
        """Convert single image to slide (validate and copy as PNG)"""
        # Open and validate
        with Image.open(image_path) as img:
            width, height = img.size
            
            # Validate aspect ratio
            aspect_name = None
            if validate_ratio:
                ar = self.validate_aspect_ratio(width, height)
                aspect_name = ar.name
            
            # Convert to RGB if necessary (for RGBA/P modes)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Save as PNG
            output_path = output_dir / "001.png"
            img.save(output_path, 'PNG', quality=95)
        
        return [output_path], aspect_name
    
    async def _pdf_to_png(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        """Convert PDF pages to PNG images"""
        # Try pdftoppm first, fallback to ImageMagick
        try:
            return await self._pdf_to_png_pdftoppm(pdf_path, output_dir)
        except FileNotFoundError:
            return await self._pdf_to_png_imagemagick(pdf_path, output_dir)
    
    async def _pdf_to_png_pdftoppm(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        """Convert using pdftoppm (faster, better quality)"""
        output_prefix = output_dir / "slide"
        
        cmd = [
            "pdftoppm",
            "-png",
            "-r", str(self.dpi),
            str(pdf_path),
            str(output_prefix)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"pdftoppm conversion failed: {stderr.decode()}")
        
        # pdftoppm creates: slide-1.png, slide-2.png, ...
        # Rename to: 001.png, 002.png, ...
        png_files = sorted(output_dir.glob("slide-*.png"))
        result = []
        
        for i, png_file in enumerate(png_files, 1):
            new_name = output_dir / f"{i:03d}.png"
            png_file.rename(new_name)
            result.append(new_name)
        
        return result
    
    async def _pdf_to_png_imagemagick(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        """Convert using ImageMagick (fallback)"""
        cmd = [
            "convert",
            "-density", str(self.dpi),
            str(pdf_path),
            "-quality", "95",
            str(output_dir / "%03d.png")
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"ImageMagick conversion failed: {stderr.decode()}")
        
        # ImageMagick creates 000.png, 001.png, ...
        # Rename to 001.png, 002.png, ...
        png_files = sorted(output_dir.glob("*.png"))
        result = []
        
        for i, png_file in enumerate(png_files, 1):
            new_name = output_dir / f"{i:03d}.png"
            if png_file != new_name:
                png_file.rename(new_name)
            result.append(new_name)
        
        return result
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute hash of file for change detection"""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def compute_slide_hash(self, image_path: Path) -> str:
        """Compute hash of slide image for change detection"""
        with open(image_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()


# Singleton instance
media_converter = MediaConverter()

