# Video-Creator Technical Specification

**Version**: 6.3 (Hardening: Celery DB singleton, Upload limits, SSRF block, Cancelled jobs)  
**Last Updated**: 2026-01-08

---

## 1. Overview

Video-Creator is a multilingual voiceover video platform that converts presentations (PPTX) into videos with synchronized narration, background music, and animated overlay elements.

### Key Features
- PPTX to video conversion
- Multi-language support with automatic translation
- Text-to-Speech (ElevenLabs)
- Background music with ducking
- **Canvas Editor** for adding animated overlays (Phase 1+)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                       │
├─────────────────────────────────────────────────────────────────┤
│  Projects List │ Editor │ Canvas Editor │ Admin │ Help          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/REST
┌──────────────────────────▼──────────────────────────────────────┐
│                    API (FastAPI + Uvicorn)                       │
├─────────────────────────────────────────────────────────────────┤
│  /api/auth │ /api/projects │ /api/slides │ /api/canvas │ ...    │
└──────┬───────────────┬──────────────────────┬───────────────────┘
       │               │                      │
       ▼               ▼                      ▼
┌──────────┐   ┌───────────────┐      ┌─────────────┐
│ PostgreSQL│   │  Redis Queue  │      │ File Storage│
│  (Data)   │   │  (Celery)     │      │  (DATA_DIR) │
└───────────┘   └───────┬───────┘      └─────────────┘
                        │
            ┌───────────┴────────────┐
            ▼                        ▼
     ┌──────────────┐        ┌──────────────┐
     │ Worker       │        │ Worker       │
     │ (TTS/Render) │        │ (Convert)    │
     └──────┬───────┘        └──────────────┘
            │ HTTP (when USE_RENDER_SERVICE=true)
            ▼
     ┌──────────────┐
     │ Render       │
     │ Service      │
     │ (Puppeteer)  │
     └──────────────┘
```

### 2.1 Render Service Architecture (Phase 5 + EPIC B)

When `USE_RENDER_SERVICE=true`, the render workflow uses browser-based rendering:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Render Service (Node.js)                      │
├─────────────────────────────────────────────────────────────────┤
│  POST /render         - Render single slide with animations      │
│  POST /render-batch   - Render multiple slides                   │
│  GET  /health         - Health check                             │
├─────────────────────────────────────────────────────────────────┤
│  1. Generate HTML with layers + CSS animations                   │
│  2. Load in Puppeteer headless browser                           │
│  3. Deterministic timeline: `window.__setTimelineTime(tMs)`       │
│  4. Capture frames in-memory (JPEG/PNG buffers)                   │
│  5. Encode directly via FFmpeg stdin pipe (image2pipe)            │
│  6. Return output path                                            │
└─────────────────────────────────────────────────────────────────┘
```

**Flow:**
1. Celery worker calls `RenderServiceClient.render_batch()` (preferred) or `render_slide()` (fallback)
2. Render service generates HTML with slide background + animated layers
3. Puppeteer pauses animations once and exposes `window.__setTimelineTime(tMs)` to step time deterministically
4. Frames are captured **in-memory** (`page.screenshot({encoding:'binary'})`) and streamed to FFmpeg via stdin (`image2pipe`)
5. FFmpeg encodes frames into a video clip (MP4/WebM)
5. Worker concatenates clips and mixes audio

**Performance Optimizations (Phase 5+ / EPIC B):**
- **Browser pool**: render-service keeps **one Chromium instance** with a **pool of pre-warmed pages** (reduces overhead per slide). Pool stats are exposed via `GET /health`.
- **Parallel batch rendering**: `POST /render-batch` supports `concurrency` and runs multiple slides in parallel (capped by `MAX_CONCURRENCY` and `POOL_SIZE`).
- **Font caching**: render-service pre-warms fontconfig cache in Docker, injects `@font-face` preload CSS, and waits for `document.fonts.ready` before capture.
- **Stream capture (EPIC B)**: no per-frame PNGs on disk; frames are piped to FFmpeg.

**Stream capture config (EPIC B)**
- `USE_STREAM_CAPTURE=true|false` (default true)
- `FRAME_FORMAT=jpeg|png` (default jpeg)
- `FRAME_QUALITY=1..100` (jpeg only; default 90)

**Important Notes (Prod/Docker):**
- Render service **does not call** `/static/slides/*` or `/static/assets/*` because those endpoints require authentication.
- Instead, the worker passes **filesystem paths** (shared `/data/projects` volume), and render-service loads them via internally-generated `file://` URLs inside Chromium.
- **Caller input rule:** callers must send **filesystem paths**. HTTP(S) URLs are rejected by default (see `BLOCK_EXTERNAL_URLS`). Supplying a `file://...` URL directly is rejected by render-service.
- Output is written to render-service `OUTPUT_DIR` (e.g. `/app/output`) and read by the worker from its mounted `RENDER_OUTPUT_DIR` (same underlying Docker volume).

**Security model (critical)**
- Render-service normalizes layer sources:
  - HTTP(S) URLs are **blocked by default** to prevent SSRF (`BLOCK_EXTERNAL_URLS=true`). Set `BLOCK_EXTERNAL_URLS=false` only in trusted dev environments.
  - `file:` URLs provided by the caller are rejected
  - Non-URL inputs are treated as filesystem paths
- All filesystem paths are validated against `ALLOWED_BASE_PATHS` (default `/data/projects`) and are additionally checked via `realpath()` to prevent symlink-bypass escapes.
- Chromium is launched with `--allow-file-access-from-files` and `--disable-web-security` for local file rendering; the whitelist above is mandatory to keep this safe.
- Render-service enforces **strict request validation** (Zod) for `layers` to prevent HTML/CSS injection:
  - `layer.id` is restricted to safe characters (`[a-zA-Z0-9_-]+`)
  - `fontFamily` is restricted to `AVAILABLE_FONTS`
  - Color fields must be hex or `rgb()/rgba()`
- **Defense in depth (backend):** the worker rewrites `/static/assets/...` URLs to filesystem paths under `DATA_DIR` and rejects any path that would escape `DATA_DIR` (including `../` traversal and absolute paths outside `DATA_DIR`).
- Backend path helpers enforce this: `to_relative_path(...)` raises for paths outside `DATA_DIR` (legacy `allow_outside=True` is reserved for migration helpers).

**DoS limits (render-service, 2026-01 hardening)**
- Render-service rejects requests exceeding configured limits (HTTP 400):
  - `duration <= MAX_DURATION` (default 300s)
  - `fps <= MAX_FPS` (default 60)
  - `width <= MAX_WIDTH`, `height <= MAX_HEIGHT` (default 3840×2160)
  - `ceil(duration * fps) <= MAX_FRAMES` (default 18000)
- `layers` count is capped (default max 100 layers per slide).

### 2.2 Canvas Editor Frontend Architecture (Fabric.js)

Canvas Editor (`frontend/src/components/canvas/CanvasEditor.tsx`) uses Fabric.js to render and edit overlay layers on top of the slide background.

**Coordinate system**
- The internal Fabric canvas coordinate system is always **1920×1080** (scene units).
- Zoom is applied as **CSS-only scaling** of the `<canvas>` element (`canvas.setDimensions(..., { cssOnly: true })`) to avoid pointer/selection drift.
- After CSS resize, Fabric offset is recalculated (`canvas.calcOffset()`) to keep mouse mapping correct.

**Layer rendering pipeline**
- Layers are rendered sorted by `zIndex` (missing `zIndex` treated as `0`).
- Visibility is treated defensively: only `visible === false` hides a layer (missing/undefined `visible` means visible).
- On every render, Fabric objects corresponding to layers are cleared and recreated (background image is preserved).

**Async image rendering (critical correctness)**
- Image layers are loaded asynchronously (`FabricImage.fromURL`).
- To prevent **z-order corruption** from late loads, after `canvas.add(img)` the object is moved to its intended `zIndex` (e.g. `img.moveTo(zIndex)` / `canvas.moveObjectTo(img, zIndex)`).
- To prevent **“ghost images”** on re-render (stale promises adding old images after the canvas has been cleared), Canvas Editor maintains a monotonically increasing **render generation token**:
  - Each `renderLayersToCanvas()` increments `renderGenRef.current` and captures the value (`gen`).
  - Each `createImageObject(..., gen)` checks `gen === renderGenRef.current` before `canvas.add(img)`.
  - If the render is stale, the loaded image is discarded.

**Selection preservation**
- Because the renderer recreates objects, selection would be lost.
- `renderLayersToCanvas(..., restoreSelectionId)` optionally restores selection by finding Fabric object with `obj.data.layerId === restoreSelectionId` and calling `canvas.setActiveObject(obj)`.

**Data binding**
- Each Fabric object stores `data.layerId` for back-references to `SlideLayer.id`.
- On `object:modified`, Canvas Editor updates the corresponding `SlideLayer` in React state:
  - `position` from `left/top`
  - `size` from `width/height * scaleX/scaleY`
  - `rotation` from `angle`

### 2.3 Backend transaction handling (FastAPI + workers)

- FastAPI DB dependency (`backend/app/db/database.py:get_db`) performs **rollback on any exception** before closing the session.
- Celery DB context manager (`backend/app/db/database.py:get_celery_db`) does the same for worker tasks, using a **singleton async engine + session factory** (NullPool) to avoid per-task engine churn/leaks.
- Celery worker disposes this engine on shutdown via `celery.signals.worker_shutdown` (best-effort cleanup).
- Goal: avoid leaked/dirty transactions and follow-up errors after request/task failures.

---

## 3. Database Schema

### 3.1 Existing Tables

| Table | Description |
|-------|-------------|
| `projects` | Main project entity |
| `project_versions` | Version snapshots |
| `slides` | Individual slides |
| `slide_scripts` | Script text per language |
| `slide_audio` | Generated TTS audio |
| `audio_assets` | Background music files |
| `project_audio_settings` | Audio/render settings |
| `project_translation_rules` | Glossary & translation rules |
| `render_jobs` | Background job tracking |

**Render job status enum (2026-01 hardening)**
- `queued` → `running` → (`done` | `failed` | `cancelled`)
- Cancel endpoints set `status="cancelled"` (not `failed`) and populate `error_message` with a cancel reason.

### 3.2 New Tables (Phase 1)

#### `slide_scenes`
Canvas scene data for each slide.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `slide_id` | UUID | FK to slides (unique) |
| `canvas_width` | INTEGER | Canvas width (default 1920) |
| `canvas_height` | INTEGER | Canvas height (default 1080) |
| `layers` | JSONB | Array of SlideLayer objects |
| `schema_version` | INTEGER | For migration compatibility |
| `render_key` | VARCHAR(64) | Hash for caching |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Defaults (DB-level)**
- For non-null columns that have defaults (e.g. `canvas_width`, `canvas_height`, `schema_version`), Postgres defaults are enforced via `server_default` so inserts are safe even outside the ORM.

#### `slide_markers`
Animation markers per slide per language.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `slide_id` | UUID | FK to slides |
| `lang` | VARCHAR(10) | Language code |
| `markers` | JSONB | Array of Marker objects |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique constraint**: `(slide_id, lang)`

#### `normalized_scripts`
Normalized script text with word timings from TTS.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `slide_id` | UUID | FK to slides |
| `lang` | VARCHAR(10) | Language code |
| `raw_text` | TEXT | Original text |
| `normalized_text` | TEXT | Processed text |
| `tokenization_version` | INTEGER | For compatibility |
| `word_timings` | JSONB | Array of WordTiming objects |
| `contains_marker_tokens` | BOOLEAN | True if `normalized_text` contains ⟦M:uuid⟧ |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique constraint**: `(slide_id, lang)`

**Marker token support (EPIC A)**
- Marker tokens are embedded in scripts as **⟦M:<uuid>⟧** and are preserved during normalization/translation.
- `tokenization_version` is bumped when token semantics change (current: 2).

#### `global_markers` (EPIC A)
Global marker IDs for a slide (language-independent).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Marker ID (global) |
| `slide_id` | UUID | FK to slides |
| `name` | VARCHAR(255) | Optional name |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `marker_positions` (EPIC A)
Marker position + computed time per language (derived deterministically via tokens + TTS timings).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `marker_id` | UUID | FK to global_markers |
| `lang` | VARCHAR(10) | Language code |
| `char_start` | INTEGER | Position in normalized_text (optional) |
| `char_end` | INTEGER | Position in normalized_text (optional) |
| `time_seconds` | FLOAT | Anchor time (filled after TTS) |
| `source` | ENUM | manual \| wordclick \| auto |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique constraint**: `(marker_id, lang)`

#### `render_cache` (EPIC B)
Cache of rendered slide segments to avoid re-rendering unchanged scenes.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `slide_id` | UUID | FK to slides |
| `lang` | VARCHAR(10) | Language code |
| `render_key` | VARCHAR(64) | Hash of scene content |
| `fps` | INTEGER | Frame rate |
| `width` | INTEGER | Output width |
| `height` | INTEGER | Output height |
| `renderer_version` | VARCHAR(20) | Renderer version (cache bust) |
| `segment_path` | VARCHAR(500) | Relative path to cached segment |
| `duration_sec` | FLOAT | Segment duration |
| `frame_count` | INTEGER | Frames rendered |
| `file_size_bytes` | INTEGER | Optional |
| `render_time_ms` | INTEGER | Optional |
| `created_at` | TIMESTAMP | |
| `last_accessed_at` | TIMESTAMP | |

**Unique constraint**: `(slide_id, lang, render_key, fps, width, height, renderer_version)`

#### `slide_scripts` additions (EPIC A)
- `needs_retranslate: BOOLEAN` — set when a script lacks marker tokens after migration, so UI can offer “Re-translate preserving markers”.

#### `assets`
Project assets for canvas (images, backgrounds, icons).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `project_id` | UUID | FK to projects |
| `type` | VARCHAR(20) | 'image', 'background', 'icon' |
| `filename` | VARCHAR(255) | Unique filename |
| `file_path` | VARCHAR(500) | Relative path |
| `thumbnail_path` | VARCHAR(500) | Thumbnail path |
| `width` | INTEGER | Image width |
| `height` | INTEGER | Image height |
| `file_size` | INTEGER | File size in bytes |
| `created_at` | TIMESTAMP | |

---

## 4. Data Models (Pydantic)

### 4.1 SlideLayer

```python
class SlideLayer:
    id: str                    # Unique layer ID
    type: "text" | "image" | "plate"
    name: str                  # Display name
    
    # Transform
    position: {x: float, y: float}
    size: {width: float, height: float}
    anchor: "topLeft" | "center" | ...
    rotation: float            # Degrees
    opacity: float             # 0-1
    
    # State
    visible: Optional[bool]     # Missing/undefined treated as visible
    locked: Optional[bool]      # Missing/undefined treated as unlocked
    zIndex: Optional[int]       # If None/missing, API normalizes ordering on save
    groupId: Optional[str]     # For grouping
    
    # Content (one of)
    text: Optional[TextContent]
    image: Optional[ImageContent]
    plate: Optional[PlateContent]
    
    # Animation
    animation: Optional[LayerAnimation]
```

### 4.2 TextContent

```python
class TextContent:
    baseContent: str           # Base language text
    translations: Dict[str, str]  # {"ru": "Привет", "de": "Hallo"}
    isTranslatable: bool
    style: TextStyle           # Font, color, alignment
    overflow: "shrinkFont" | "expandHeight" | "clip"
    minFontSize: float
```

### 4.3 AnimationConfig

```python
class AnimationConfig:
    type: "fadeIn" | "fadeOut" | "slideLeft" | "slideRight" | ...
    duration: float            # Seconds
    delay: float               # Seconds
    easing: "linear" | "easeIn" | "easeOut" | "easeInOut"
    trigger: AnimationTrigger
```

### 4.4 AnimationTrigger

```python
class AnimationTrigger:
    type: "time" | "marker" | "start" | "end" | "word"
    
    # For type="time"
    seconds: Optional[float]
    
    # For type="marker"
    markerId: Optional[str]
    
    # For type="start"/"end"
    offsetSeconds: Optional[float]
    
    # For type="word"
    charStart: Optional[int]   # Character offset in normalized text
    charEnd: Optional[int]
    wordText: Optional[str]
```

**EPIC A note (stable multi-language triggers)**
- **Canonical persisted trigger** is `type="marker"` with `markerId=<GlobalMarker.id>`.
- `type="word"` is treated as **legacy/UI-only** and is migrated to markers via `POST /scene/migrate-triggers`.
- Cross-language resolution must NOT rely on base-language `charStart` heuristics; the stable anchor is the marker token ⟦M:<uuid>⟧ + per-language `marker_positions.time_seconds`.

### 4.5 Marker

```python
class Marker:
    id: str
    name: Optional[str]
    charStart: int             # Position in normalized text
    charEnd: int
    wordText: str
    timeSeconds: Optional[float]  # Populated after TTS
```

**Legacy vs EPIC A**
- `Marker` above represents legacy `slide_markers.markers[*]` entries.
- EPIC A uses **GlobalMarker + MarkerPosition** as the stable cross-language representation.

### 4.6 WordTiming

```python
class WordTiming:
    charStart: int
    charEnd: int
    startTime: float           # Seconds
    endTime: float
    word: str
```

---

## 5. API Endpoints

### 5.0 Validation & error semantics

- `lang` parameters are normalized to lowercase and validated via `validate_lang_code(...)`:
  - Format: 2–3 lowercase letters
  - Must be in global `SUPPORTED_LANGUAGES` allowlist
  - Invalid/unsupported values return **HTTP 400**
- Enum-like fields in settings updates are validated:
  - `ducking_strength` (`DuckingStrength`)
  - `transition_type` (`TransitionType`)
  - Invalid values return **HTTP 400** (not 500)

### 5.1 Canvas API (`/api/canvas`)

#### Scenes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/slides/{slide_id}/scene` | Get scene (creates default if none) |
| PUT | `/slides/{slide_id}/scene` | Update entire scene |
| POST | `/slides/{slide_id}/scene/layers` | Add new layer |
| PUT | `/slides/{slide_id}/scene/layers/reorder` | Reorder layers |
| PUT | `/slides/{slide_id}/scene/layers/{layer_id}` | Update layer |
| DELETE | `/slides/{slide_id}/scene/layers/{layer_id}` | Delete layer |

#### Translation & Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/slides/{slide_id}/scene/translate` | Translate text layers to target language |
| GET | `/slides/{slide_id}/scene/resolved?lang=` | Get scene with word triggers resolved to time-based |

**Implementation note (compatibility):**
- `TranslateAdapter.translate_batch()` is treated as backward-compatible in the API layer:
  - Current adapter returns `List[Tuple[str, meta]]`
  - Some tests/mocks historically return `(List[str], meta)`
  - The route accepts both shapes and extracts the translated text list accordingly.

**Translate Request:**
```json
{ "target_lang": "ru" }
```

**Translate Response:**
```json
{
  "translated_count": 2,
  "target_lang": "ru",
  "layers_updated": ["layer-1", "layer-2"]
}
```

**Resolved Scene Response:**
```json
{
  "id": "...",
  "slide_id": "...",
  "canvas": {"width": 1920, "height": 1080},
  "layers": [...],
  "lang": "ru",
  "triggers_resolved": 3,
  "schema_version": 1,
  "render_key": "abc123",
  "voice_offset_applied": 0.0
}
```

**Trigger resolution notes (multi-language, EPIC A)**
- Stable cross-language timing uses **GlobalMarker IDs + marker tokens**:
  - Token format in scripts: **⟦M:<uuid>⟧**
  - Per-language timing is stored in `marker_positions.time_seconds` (computed after TTS).
- Resolution behavior:
  - `type="marker"` → resolved strictly via `marker_positions.time_seconds`
  - `type="word"` + `markerId` → resolved via the same marker time (legacy compatibility)
  - `type="word"` without markerId → resolved only by exact `charStart` match in `normalized_scripts.word_timings` (base language). **No “примерно там” heuristics.**
- To match final render timing, clients may pass `voice_offset_sec` to `/scene/resolved` (pre-padding offset before voice starts).

#### Markers

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/slides/{slide_id}/markers/{lang}/create-from-word` | **EPIC A**: create GlobalMarker + base MarkerPosition from offsets |
| GET | `/slides/{slide_id}/global-markers` | **EPIC A**: list GlobalMarkers + positions |
| POST | `/slides/{slide_id}/markers/{lang}/compute-times` | **EPIC A**: recompute `marker_positions.time_seconds` after TTS |
| POST | `/slides/{slide_id}/script/{lang}/insert-marker-tokens` | **EPIC A**: insert ⟦M:uuid⟧ tokens into script text |
| POST | `/slides/{slide_id}/scene/migrate-triggers` | **EPIC A**: migrate legacy word triggers → markerId + tokens |
| GET | `/slides/{slide_id}/markers/{lang}` | Legacy: get `slide_markers` |
| PUT | `/slides/{slide_id}/markers/{lang}` | Legacy: update `slide_markers` |
| POST | `/slides/{slide_id}/markers/propagate?source_lang=&target_lang=` | Legacy (deprecated): best-effort marker propagation |

#### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{project_id}/assets` | List assets |
| POST | `/projects/{project_id}/assets` | Upload asset |
| DELETE | `/assets/{asset_id}` | Delete asset |

**Upload hard limits (DoS protection)**
- Max upload size: **25 MB** (reject with **HTTP 413**)
- Max image pixels: **100,000,000** (reject with **HTTP 400**, decompression-bomb protection)

#### Normalized Scripts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/slides/{slide_id}/script/{lang}/normalized` | Get with timings |

### 5.2 Static Files

| Endpoint | Description |
|----------|-------------|
| `/static/assets/{project_id}/{filename}` | Serve asset |
| `/static/assets/{project_id}/thumbs/{filename}` | Serve thumbnail |

---

## 6. ElevenLabs Integration

### 6.1 TTS with Timestamps

The TTS adapter supports `convert_with_timestamps` endpoint:

```python
response = client.text_to_speech.convert_with_timestamps(
    text=text,
    voice_id=voice_id,
    model_id=model,
)

# Response includes:
# - audio_base64: Base64-encoded audio
# - alignment: Character-level timing data
#   - characters: ["H", "e", "l", "l", "o", ...]
#   - character_start_times_seconds: [0.0, 0.1, ...]
#   - character_end_times_seconds: [0.1, 0.2, ...]
```

### 6.2 Word Timing Extraction

Character-level timings are aggregated to word-level:

```python
# Input: normalized text + ElevenLabs alignment
# Output: List[WordTiming]

[
    {"charStart": 0, "charEnd": 5, "word": "Hello", "startTime": 0.0, "endTime": 0.5},
    {"charStart": 6, "charEnd": 11, "word": "world", "startTime": 0.5, "endTime": 1.0}
]
```

### 6.3 Fallback Timing Estimation

When ElevenLabs alignment is unavailable, timings are estimated proportionally:

```python
# word_duration = (word_char_count / total_char_count) * total_audio_duration
```

### 6.4 Persistence (worker) — timings + marker timeSeconds

When a slide’s TTS is generated for a language:
- The worker calls `generate_speech_with_timestamps(...)` to retrieve optional alignment data.
- Word timings are computed:
  - Prefer `align_word_timings(normalized_text, alignment)` when alignment exists.
  - Fall back to `estimate_word_timings(normalized_text, duration)` otherwise.
- The worker **upserts** `normalized_scripts` for `(slide_id, lang)` with `{raw_text, normalized_text, word_timings}`.
- EPIC A: The worker updates marker timing in two layers:
  - **Global markers**: updates `marker_positions.time_seconds` deterministically using marker tokens ⟦M:<uuid>⟧ + `word_timings`.
  - **Legacy markers**: best-effort updates `slide_markers.markers[*].timeSeconds` for backward compatibility (charStart first; optional wordText fallback).

---

## 7. Text Normalization

### 7.1 Normalization Rules

1. Unicode NFC normalization
2. Smart quotes → straight quotes
3. Em/en dashes → hyphens
4. Ellipsis → three dots
5. Multiple spaces → single space
6. Non-breaking spaces → regular spaces
7. Trim whitespace
8. **EPIC A:** Marker tokens **⟦M:<uuid>⟧ are preserved exactly** (not translated/modified)

### 7.2 Tokenization

Words are extracted with character offsets:

```python
tokenize_words("Hello world") 
# → [(0, 5, "Hello"), (6, 11, "world")]
```

**EPIC A tokenization note**
- `tokenize_words(..., skip_marker_tokens=True)` skips marker-token fragments so UUIDs inside ⟦M:...⟧ don’t appear as “words”.

---

## 8. Render Key (Caching)

The `render_key` is a SHA256 hash of scene content:

```python
content = json.dumps({"layers": layers, "canvas": canvas}, sort_keys=True)
render_key = hashlib.sha256(content.encode()).hexdigest()[:16]
```

Used to:
- Skip re-rendering unchanged scenes
- Cache rendered scene frames/video segments

**EPIC B caching layers**
- **Filesystem clip cache (current default)**: worker stores per-slide segments under `DATA_DIR/{project}/versions/{version}/clips/{lang}/{slideId}_{lang}_{render_key}.webm`.
- **DB cache table (render_cache)**: records cache metadata keyed by `(slide_id, lang, render_key, fps, resolution, renderer_version)` for audit/cleanup and future cross-run cache policies.

---

## 9. File Structure

```
DATA_DIR/
├── {project_id}/
│   ├── versions/
│   │   └── {version_id}/
│   │       ├── slides/
│   │       │   ├── 001.png
│   │       │   └── slide_{uuid}.png
│   │       ├── audio/
│   │       │   └── {lang}/
│   │       │       └── slide_{uuid}.wav
│   │       ├── clips/                    # EPIC B: cached slide segments (render-service output copied here)
│   │       │   └── {lang}/
│   │       │       └── {slide_id}_{lang}_{render_key}.webm
│   │       └── render/
│   │           └── {lang}/
│   │               └── video.mp4
│   ├── assets/                    # NEW
│   │   ├── {uuid}.png
│   │   └── thumbs/
│   │       └── {uuid}.png
│   └── music/
│       └── corporate.mp3
```

---

## 10. Phase Roadmap

### ✅ Phase 1: Backend Foundation (COMPLETE)
- [x] Database migrations
- [x] Pydantic schemas
- [x] Canvas API endpoints
- [x] ElevenLabs word timings
- [x] Text normalization
- [x] Unit & integration tests (18 new, 150 total)

### ✅ Phase 2: Frontend Canvas Editor (COMPLETE)
- [x] Fabric.js v6 integration
- [x] Canvas component with zoom controls
- [x] Layer panel (list, visibility, lock, z-order, drag reorder)
- [x] Properties panel (transform, text, plate styling)
- [x] Asset library modal (upload, delete, thumbnails)
- [x] API client methods for canvas endpoints
- [x] Integration into slide editor page

### ✅ Phase 3: Animation System (COMPLETE)
- [x] Animation settings UI in PropertiesPanel (entrance/exit animations)
- [x] Trigger configuration (time, marker, word, start/end with offsets)
- [x] Word picker in MarkersManager (click word to create marker)
- [x] MarkersManager component (add, edit, delete markers)
- [x] AnimationPreview component (timeline preview, layer state indicators)
- [x] Animation style calculation (`getLayerAnimationStyle`)
- [x] Frontend tests (10 animation + 7 markers = 17 new tests)

### ✅ Phase 4: Multi-language Canvas (COMPLETE)
- [x] Backend: `POST /canvas/slides/{id}/scene/translate` endpoint
- [x] Auto-translate translatable text layers using project glossary
- [x] Language switcher in CanvasEditor toolbar
- [x] Display translated text based on selected language
- [x] Backend tests for translate endpoint (2 new tests)
- [x] Text overflow handling: `shrinkFont` (auto-reduce font), `expandHeight`, `clip`
- [x] Backend: `GET /canvas/slides/{id}/scene/resolved?lang=` - word→time trigger conversion
- [x] Frontend: Animation Preview uses resolved scene when there are no unsaved changes (more accurate timings)
- [x] Backend tests for resolved scene endpoint (2 new tests)

### ✅ Phase 5: Browser-Based Render (COMPLETE)
- [x] Node.js render service (`render-service/`) with Express + Puppeteer
- [x] Frame-by-frame capture with Web Animations API (`currentTime`)
- [x] HTML template generation for slides with animated layers
- [x] FFmpeg encoding (WebM VP9 or MP4 H.264)
- [x] Docker configuration (`render-service/Dockerfile`)
- [x] Integration into `docker-compose.prod.yml`
- [x] Backend `RenderServiceClient` adapter (`app/adapters/render_service.py`)
- [x] Celery task integration with fallback to FFmpeg-only render
- [x] Caching by `render_key` hash
- [x] `USE_RENDER_SERVICE` feature flag (default: off)

### ✅ Phase 6: Music & Polish (COMPLETE)
- [x] Music fade in/out (`music_fade_in_sec`, `music_fade_out_sec`)
- [x] Ducking controls (already implemented: `ducking_enabled`, `ducking_strength`)
- [x] Transition presets (already implemented: none/fade/crossfade + duration)
- [x] Fonts system (Inter, Roboto, Open Sans, Lato, DejaVu Sans installed in render-service)

---

## 11. Testing

### Test Coverage (Current)

| Area | Suite | Count | Status |
|------|-------|-------|--------|
| Backend | `pytest` | 335 | ✅ Pass |
| Frontend unit | `vitest` (excludes `frontend/e2e/**`) | 40 | ✅ Pass |
| Render-service unit | `vitest` | 11 | ✅ Pass |

> Note: Playwright E2E specs live under `frontend/e2e/**` and must be run via `npx playwright test` (they are intentionally excluded from Vitest).

### 11.1 Frontend audit hardening (2026-01-08)

- **Admin Jobs list correctness**: keyed `React.Fragment` used for `(job) => (...)` rows to avoid React key warnings and reconcile edge-cases; `target="_blank"` download links include `rel="noreferrer noopener"`.
- **Workspace downloads**: download URLs use API-provided filenames (e.g. `video_file`) instead of guessing.
- **CSRF retry safety**: Axios interceptor retries CSRF refresh at most once per request (guard flag) to avoid infinite loops on persistent 403 CSRF.
- **Project editor robustness**: conversion polling timers are cleaned up on unmount; slide-status refresh is batched (limits parallelism); audio summary is computed against `slides` (handles partial status loads).
- **Canvas Editor UX**: newly added layer becomes the active Fabric selection; duplicate layer preserves z-order intent (`zIndex`).
- **Deployment**: `frontend/Dockerfile.prod` healthcheck uses Node’s built-in `fetch` (no Alpine `wget` dependency); `next.config.js` safely parses `NEXT_PUBLIC_API_URL` for image hostnames; ESLint is enforced during `next build`.

### Running Tests

```bash
cd backend
source venv/bin/activate
python -m pytest --tb=short
```

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

```bash
cd render-service
npm run typecheck
npm test
# NOTE: lint requires devDependencies installed
npm run lint
```

---

## 12. Audio Settings

### Music Fade In/Out

The `ProjectAudioSettings` model includes:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `music_fade_in_sec` | float | 2.0 | Duration of fade-in at video start |
| `music_fade_out_sec` | float | 3.0 | Duration of fade-out at video end |

Implemented via FFmpeg `afade` filter in the audio mix pipeline:
```
afade=t=in:st=0:d=2.0,afade=t=out:st={voice_duration-3.0}:d=3.0
```

### Ducking

Ducking automatically reduces music volume during speech using FFmpeg's `sidechaincompress`:

| Strength | Threshold | Ratio | Attack | Release |
|----------|-----------|-------|--------|---------|
| Light | 0.1 | 3:1 | 5ms | 300ms |
| Default | 0.05 | 6:1 | 3ms | 200ms |
| Strong | 0.02 | 10:1 | 2ms | 150ms |

---

## 13. Available Fonts (Render Service)

The render-service Docker image includes these fonts for text layer rendering:

| Font | Package |
|------|---------|
| **Inter** | Downloaded from GitHub releases |
| **Roboto** | `fonts-roboto` |
| **Open Sans** | `fonts-open-sans` |
| **Lato** | `fonts-lato` |
| **DejaVu Sans** | `fonts-dejavu` |
| **Liberation Sans** | `fonts-liberation` |
| **Noto Sans CJK** | `fonts-noto-cjk` (Chinese, Japanese, Korean) |

Text layers use a fallback chain: `fontFamily → Inter → Roboto → Open Sans → Lato → Noto Sans → Liberation Sans → DejaVu Sans → sans-serif`

**Frontend ↔ render-service consistency**
- The frontend font dropdown (`frontend/src/components/canvas/PropertiesPanel.tsx`) must only expose fonts that are installed in the render-service Docker image.
- Render-service exports the authoritative list as `AVAILABLE_FONTS` (`render-service/src/renderer.ts`). Update both the Docker image and this list when adding/removing fonts.

---

## 14. Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `OPENAI_API_KEY` | OpenAI API key (translation) |
| `ADMIN_USERNAME` | Admin login |
| `ADMIN_PASSWORD` | Admin password |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data/projects` | Data storage path |
| `DEBUG` | `false` | Enable debug mode |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed origins |
| `USE_RENDER_SERVICE` | `false` | Enable browser-based rendering with animations |
| `RENDER_SERVICE_URL` | `http://render-service:3001` | Base URL for render-service |
| `RENDER_SERVICE_TIMEOUT_SEC` | `600` | Timeout (seconds) for a single slide render request |
| `RENDER_SERVICE_BATCH_CONCURRENCY` | `3` | Concurrency hint for `/render-batch` |
| `POOL_SIZE` | `3` | (render-service) Number of pre-warmed Puppeteer pages in the pool |
| `MAX_CONCURRENCY` | `3` | (render-service) Maximum parallel slide renders in `/render-batch` |
| `MAX_DURATION` | `300` | (render-service) Upper bound for `duration` (seconds) to prevent render DoS |
| `MAX_FPS` | `60` | (render-service) Upper bound for `fps` |
| `MAX_WIDTH` | `3840` | (render-service) Upper bound for render width (pixels) |
| `MAX_HEIGHT` | `2160` | (render-service) Upper bound for render height (pixels) |
| `MAX_FRAMES` | `18000` | (render-service) Upper bound for total frames (`ceil(duration * fps)`) |
| `PUPPETEER_PROTOCOL_TIMEOUT_MS` | `600000` | (render-service) CDP protocol timeout to avoid long render timeouts |
| `ALLOWED_BASE_PATHS` | `/data/projects` | (render-service) Comma-separated whitelist for filesystem reads. Paths outside are rejected (prevents path traversal). |
| `BLOCK_EXTERNAL_URLS` | `true` | (render-service) **SSRF protection**: when true, reject any `http:`/`https:` asset URLs and require filesystem paths. Set to `false` only for trusted dev. |
| `OUTPUT_DIR` | `/app/output` | (render-service) Output directory for rendered clips. Must be mounted/shared with worker in Docker. |
| `TMP_DIR` | `/app/tmp` | (render-service) Temp directory for per-render frames. |
| `PUPPETEER_EXECUTABLE_PATH` | *(unset)* | (render-service) Override Chromium path in Docker/runtime. |

**Note (paths with spaces)**
- If `DATA_DIR` contains spaces, quote it in `.env` / docker-compose env_file, e.g. `DATA_DIR="/Users/.../My Code/..."`

---

## 15. Deployment Hardening (Production)

### 15.1 `.env.prod` handling (no `source`)

- Production scripts (`deploy/deploy.sh`, `deploy/backup.sh`, `deploy/restore.sh`) treat `.env.prod` as **data**, not executable code (avoid `source` to reduce RCE risk).

### 15.2 Backups: `.env.prod` is plaintext

- `deploy/backup.sh` includes `.env.prod` in the backup archive as **plaintext** (file permission hardened with `chmod 600`).
- For off-site storage, encrypt the archive (recommended: `age` or `gpg`) and store keys separately.

### 15.3 Deploy health checks (no false “healthy”)

- `deploy/deploy.sh` validates **each critical service** health status via `docker inspect` (instead of grepping compose output).

### 15.4 Caddy security headers baseline

- Caddy sets baseline security headers including **HSTS**, **X-Frame-Options**, **X-Content-Type-Options**, **Referrer-Policy**, **CSP**, **Permissions-Policy**, **COOP/COEP**.
- CSP is initially permissive to avoid breaking the Next.js app; tighten gradually as you enumerate required sources.

### 15.5 Compose resource limits note

- `deploy.resources.limits` in `docker-compose.prod.yml` are enforced **only in Docker Swarm mode**.
- If running standalone `docker compose`, enforce limits via host sizing, an orchestrator, or Compose-supported resource flags (document your chosen approach).

*Document maintained as part of Phase 6 deliverable.*
