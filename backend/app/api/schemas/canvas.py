"""
Pydantic schemas for Canvas Editor (Phase 1)
"""
from typing import Optional, List, Dict, Literal, Union
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


# === Position & Size ===

class Position(BaseModel):
    x: float = 0
    y: float = 0


class Size(BaseModel):
    width: float = 100
    height: float = 100


# === Text Content ===

class TextStyle(BaseModel):
    fontFamily: str = "Inter"
    fontSize: float = 24
    fontWeight: Literal["normal", "bold"] = "normal"
    fontStyle: Literal["normal", "italic"] = "normal"
    color: str = "#000000"
    align: Literal["left", "center", "right"] = "left"
    verticalAlign: Literal["top", "middle", "bottom"] = "top"
    lineHeight: float = 1.4


class TextContent(BaseModel):
    baseContent: str = ""
    translations: Dict[str, str] = Field(default_factory=dict)  # {"zh": "你好", "de": "Hallo"}
    isTranslatable: bool = True
    style: TextStyle = Field(default_factory=TextStyle)
    overflow: Literal["shrinkFont", "expandHeight", "clip"] = "shrinkFont"
    minFontSize: float = 12


# === Image Content ===

class ImageContent(BaseModel):
    assetId: str
    assetUrl: str = ""
    fit: Literal["contain", "cover", "fill"] = "contain"


# === Plate Content ===

class PlateAccent(BaseModel):
    position: Literal["left", "top", "right", "bottom"] = "left"
    width: float = 4
    color: str = "#3B82F6"


class PlateBorder(BaseModel):
    width: float = 1
    color: str = "#E5E7EB"
    style: Literal["solid", "dashed"] = "solid"


class PlatePadding(BaseModel):
    top: float = 16
    right: float = 16
    bottom: float = 16
    left: float = 16


class PlateContent(BaseModel):
    backgroundColor: str = "#FFFFFF"
    backgroundOpacity: float = 1.0
    borderRadius: float = 8
    border: Optional[PlateBorder] = None
    accent: Optional[PlateAccent] = None
    padding: PlatePadding = Field(default_factory=PlatePadding)


# === Animation ===

class AnimationTrigger(BaseModel):
    type: Literal["time", "marker", "start", "end", "word"]
    
    # For type="time"
    seconds: Optional[float] = None
    
    # For type="marker"
    markerId: Optional[str] = None
    
    # For type="start"/"end"
    offsetSeconds: Optional[float] = 0
    
    # For type="word" — store char offsets, not wordIndex!
    charStart: Optional[int] = None
    charEnd: Optional[int] = None
    wordText: Optional[str] = None


class AnimationFrom(BaseModel):
    """Starting state for animation (for future expansion)"""
    x: Optional[float] = None
    y: Optional[float] = None
    opacity: Optional[float] = None
    scale: Optional[float] = None


class AnimationConfig(BaseModel):
    type: Literal["fadeIn", "fadeOut", "slideLeft", "slideRight", "slideUp", "slideDown", "none"] = "none"
    duration: float = 0.5
    delay: float = 0
    easing: Literal["linear", "easeIn", "easeOut", "easeInOut"] = "easeOut"
    trigger: AnimationTrigger = Field(default_factory=lambda: AnimationTrigger(type="start", offsetSeconds=0))
    fromState: Optional[AnimationFrom] = None


class LayerAnimation(BaseModel):
    entrance: Optional[AnimationConfig] = None
    exit: Optional[AnimationConfig] = None


# === Layer ===

class SlideLayer(BaseModel):
    id: str
    type: Literal["text", "image", "plate"]
    name: str = "Layer"
    
    # Transform
    position: Position = Field(default_factory=Position)
    size: Size = Field(default_factory=Size)
    anchor: Literal["topLeft", "center", "topCenter", "bottomCenter", "topRight", "bottomLeft", "bottomRight"] = "topLeft"
    rotation: float = 0
    opacity: float = 1.0
    
    # State
    visible: bool = True
    locked: bool = False
    zIndex: Optional[int] = None  # None means "auto-assign", 0 is valid bottom layer
    groupId: Optional[str] = None
    
    # Content (one of)
    text: Optional[TextContent] = None
    image: Optional[ImageContent] = None
    plate: Optional[PlateContent] = None
    
    # Animation
    animation: Optional[LayerAnimation] = None


# === Scene ===

class CanvasSettings(BaseModel):
    width: int = 1920
    height: int = 1080


class SlideSceneBase(BaseModel):
    canvas: CanvasSettings = Field(default_factory=CanvasSettings)
    layers: List[SlideLayer] = Field(default_factory=list)


class SlideSceneCreate(SlideSceneBase):
    pass


class SlideSceneUpdate(BaseModel):
    canvas: Optional[CanvasSettings] = None
    layers: Optional[List[SlideLayer]] = None


class SlideSceneRead(SlideSceneBase):
    id: UUID
    slide_id: UUID
    schema_version: int = 1
    render_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Markers ===

class Marker(BaseModel):
    id: str
    name: Optional[str] = None
    charStart: int
    charEnd: int
    wordText: str
    timeSeconds: Optional[float] = None  # Populated after TTS


class SlideMarkersBase(BaseModel):
    markers: List[Marker] = Field(default_factory=list)


class SlideMarkersCreate(SlideMarkersBase):
    pass


class SlideMarkersUpdate(SlideMarkersBase):
    pass


class SlideMarkersRead(SlideMarkersBase):
    id: UUID
    slide_id: UUID
    lang: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Word Timings (from ElevenLabs) ===

class WordTiming(BaseModel):
    charStart: int
    charEnd: int
    startTime: float  # seconds
    endTime: float    # seconds
    word: str


class NormalizedScriptBase(BaseModel):
    raw_text: str = ""
    normalized_text: str = ""
    tokenization_version: int = 1
    word_timings: Optional[List[WordTiming]] = None


class NormalizedScriptRead(NormalizedScriptBase):
    id: UUID
    slide_id: UUID
    lang: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Assets ===

class AssetBase(BaseModel):
    type: Literal["image", "background", "icon"] = "image"
    filename: str


class AssetCreate(AssetBase):
    pass


class AssetRead(AssetBase):
    id: UUID
    project_id: UUID
    file_path: str
    thumbnail_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    url: str = ""  # Computed URL for serving
    thumbnail_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AssetListResponse(BaseModel):
    assets: List[AssetRead]
    total: int

