# 🎬 Presentation → Multilingual Voiceover Video Platform

> Веб-приложение для создания мультиязычных видео-презентаций с озвучкой на базе rsrohan99/presenter

---

## ⚠️ Known Issues (Canvas Editor)

> **Статус:** В разработке. Canvas Editor работает частично.

| Проблема | Описание |
|----------|----------|
| **Многострочный текст** | Текст не сохраняется корректно, если он содержит несколько строк (line breaks теряются) |
| **Размер шрифта** | Font size в Properties Panel применяется некорректно или сбрасывается |
| **Анимации** | Animation effects (fadeIn, slideIn, etc.) не работают в рендере |
| **Якоря (Anchors)** | Нет возможности установить anchor point для синхронизации анимации с аудио-маркерами |
| **Длительность сцены** | Нет UI для установки duration слайда без озвучки (сейчас зависит только от длины аудио) |
| **Preview vs Render** | Preview в Canvas Editor может отличаться от финального рендера |

### Roadmap для Canvas Editor
- [ ] Исправить сохранение многострочного текста
- [ ] Стабилизировать применение fontSize при resize
- [ ] Реализовать anchor points для text layers → audio markers sync
- [ ] Добавить UI для manual scene duration override
- [ ] Интеграция анимаций в render-service

---

## 🎯 Что делает платформа

1. **Upload PPTX** → автоматическая конвертация в PNG слайды
2. **Script Editor** → редактирование сценария для каждого слайда
3. **Multi-language** → перевод через OpenAI с глоссарием
4. **TTS** → озвучка через ElevenLabs (с кэшированием)
5. **Audio Mix** → музыка + ducking + loudness normalization
6. **Export** → MP4 видео + SRT субтитры для каждого языка

---

## 📁 Структура проекта

```
/
├── backend/                    # FastAPI + Celery
│   ├── app/
│   │   ├── api/               # REST endpoints
│   │   ├── core/              # Config, security
│   │   ├── db/                # SQLAlchemy models
│   │   ├── services/          # Business logic
│   │   ├── workers/           # Celery tasks
│   │   └── adapters/          # presenter integration
│   │       ├── tts.py         # ElevenLabs adapter
│   │       ├── render.py      # FFmpeg render
│   │       └── translate.py   # OpenAI translation
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Next.js
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── data/                       # Local file storage (gitignored)
│   └── projects/
│       └── {project_id}/
│           └── versions/
│               └── {version_id}/
│                   ├── input.pptx
│                   ├── slides/
│                   │   ├── 001.png
│                   │   └── ...
│                   ├── audio/
│                   │   └── {lang}/
│                   │       └── slide_001.wav
│                   ├── timelines/
│                   │   ├── voice_timeline_{lang}.wav
│                   │   ├── music_timeline.wav
│                   │   └── final_audio_{lang}.wav
│                   └── exports/
│                       └── {lang}/
│                           ├── deck_{lang}.mp4
│                           └── deck_{lang}.srt
├── docker-compose.yml
└── README.md
```

---

## ⚙️ Константы и настройки по умолчанию

### Video Output
| Параметр | Значение |
|----------|----------|
| **Resolution** | 1920×1080 (16:9) |
| **FPS** | 30 |
| **Codec** | H.264 (libx264) |
| **Audio Codec** | AAC 192kbps |

### Timing
| Параметр | Значение |
|----------|----------|
| **Pre-padding** | 3.0 sec |
| **Post-padding** | 3.0 sec |
| **First slide hold** | 1.0 sec |
| **Last slide hold** | 1.0 sec |
| **Transition type** | fade |
| **Transition duration** | 0.5 sec |

### Audio Mix
| Параметр | Значение |
|----------|----------|
| **Target loudness** | -14 LUFS |
| **Voice gain (default)** | 0 dB |
| **Music gain (default)** | -22 dB |
| **Ducking** | enabled |
| **Ducking strength** | default |

### Limits
| Параметр | Значение |
|----------|----------|
| **Max slides** | unlimited |
| **Max total duration** | unlimited |
| **Max languages** | unlimited |

### Data Directory
```
DATA_DIR=/data/projects
```

---

## 🛠 Технологический стек

### Backend
- **Python 3.11+**
- **FastAPI** — REST API
- **PostgreSQL** — основная БД
- **SQLAlchemy 2.0** — ORM
- **Celery + Redis** — очередь задач
- **FFmpeg** — рендер видео, audio mix
- **LibreOffice Headless** — PPTX → PDF → PNG
- **python-pptx** — извлечение speaker notes
- **ElevenLabs API** — TTS
- **OpenAI API** — перевод

### Frontend
- **Next.js 14** (App Router)
- **React 18**
- **TypeScript**
- **Tailwind CSS**
- **shadcn/ui**
- **Fabric.js** — Canvas Editor

### Render Service
- **Node.js** — отдельный сервис для рендера слайдов
- **Puppeteer** — headless Chrome для HTML → PNG/Video
- **Express** — HTTP API для вызова из backend

---

## 🔧 Конфигурация (.env)

- **Backend**: скопируйте `backend/env.example` → `backend/.env` и заполните ключи.
- **Frontend**: создайте `frontend/.env.local` и укажите `NEXT_PUBLIC_API_URL` (обычно `http://localhost:8000`).
- **Полный гайд по запуску**: см. `STARTUP.md`.

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/presenter

# Redis
REDIS_URL=redis://localhost:6379/0

# APIs
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...

# Storage
DATA_DIR=/data/projects

# Optional: Auth (single admin)
ADMIN_PASSWORD=...

# TTS defaults
DEFAULT_VOICE_ID=1SM7GgM6IMuvQlz2BwM3
DEFAULT_TTS_MODEL=eleven_flash_v2_5

# Translation defaults
TRANSLATION_MODEL=gpt-4o
```

---

## 📊 Модель данных

### Projects
```
id, name, base_language, current_version_id, created_at, updated_at
```

### ProjectVersions
```
id, project_id, version_number, pptx_asset_path, slides_hash, status, created_at, comment
```

### Slides
```
id, project_id, version_id, slide_index, image_path, preview_path?, notes_text, slide_hash, created_at
```

### SlideScripts
```
id, slide_id, lang, text, source (manual|imported_notes|translated), translation_meta_json, updated_at
```

### SlideAudio
```
id, slide_id, lang, voice_id, audio_path, duration_sec, audio_hash, script_text_hash, created_at
```

### SlideScenes (Canvas Editor)
```
id, slide_id, canvas {width, height}, layers[], schema_version, render_key, created_at, updated_at
```

### SlideLayer (в SlideScene.layers[])
```
id, type (text|plate|image), name, position {x, y}, size {width, height},
rotation, opacity, visible, locked, zIndex,
text? {baseContent, translations, isTranslatable, style, overflow, minFontSize},
plate? {backgroundColor, backgroundOpacity, borderRadius, border, padding},
image? {assetId, assetUrl, fit},
animation? {entrance, exit}
```

### AudioAssets
```
id, project_id, type (music), file_path, original_format, duration_sec, created_at
```

### ProjectAudioSettings
```
project_id, background_music_enabled, music_asset_id, voice_gain_db, music_gain_db, 
ducking_enabled, ducking_strength, target_lufs
```

### ProjectTranslationRules
```
project_id, do_not_translate[], preferred_translations[], style, extra_rules
```

### RenderJobs
```
id, project_id, version_id, lang, job_type, status, progress_pct, logs_path,
output_video_path, output_srt_path, started_at, finished_at
```

---

## 🚀 Запуск

### Development
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev
```

### Docker
```bash
docker-compose up -d
```

---

## 🔄 Celery Tasks

| Task | Описание | Retry |
|------|----------|-------|
| `convert_pptx_task` | PPTX → PNG + extract notes | 1 |
| `tts_slide_task` | Generate TTS for slide/lang | 3 |
| `tts_batch_task` | Generate TTS for all slides in version/lang | 1 |
| `translate_batch_task` | Translate all slides to target language | 1 |
| `render_language_task` | Build timeline + mix + render MP4 | 1 |

---

## 🔤 Шрифты (обязательные)

Установить на сервере:
- Inter
- Roboto  
- Open Sans
- Noto Sans
- Sans-serif (fallback)

```dockerfile
# В Dockerfile
RUN apt-get install -y fonts-inter fonts-roboto fonts-open-sans fonts-noto
```

---

## 📝 Glossary & Translation Rules

Per-project настройки перевода:

```json
{
  "do_not_translate": ["IFRS", "CSRD", "ESG", "KPI", "EBITDA"],
  "preferred_translations": [
    {"term": "materiality", "lang": "ru", "translation": "существенность"},
    {"term": "materiality", "lang": "uk", "translation": "суттєвість"}
  ],
  "style": "formal",
  "extra_rules": "Preserve all numbers and percentages as-is"
}
```

---

## 🎨 Canvas Editor

Визуальный редактор слоёв поверх слайда с поддержкой текста, плашек и изображений.

### Типы слоёв
| Тип | Описание |
|-----|----------|
| **Text** | Многоязычный текст с настройками шрифта |
| **Plate** | Цветная плашка с opacity, border radius |
| **Image** | Загружаемое изображение из Asset Library |

### Текстовые слои

#### Overflow режимы
| Режим | Поведение |
|-------|-----------|
| **expandHeight** (default) | Выбранный fontSize сохраняется, высота блока увеличивается под текст |
| **shrinkFont** | Автоматически уменьшает fontSize чтобы текст влез в заданные размеры |
| **clip** | Обрезает текст по границам блока |

#### Resize поведение
- При drag-resize текстового блока **fontSize масштабируется пропорционально**
- Используется geometric mean (`√(scaleX × scaleY)`) для балансировки
- После отпускания мыши fontSize сохраняется (не откатывается)
- Границы fontSize: 8–256 px

#### Мультиязычность
- `baseContent` — текст на базовом языке проекта
- `translations` — словарь переводов `{ "ru": "...", "en": "..." }`
- Переводы создаются через кнопку "Translate" в тулбаре

### Анимации слоёв
| Эффект | Описание |
|--------|----------|
| fadeIn/fadeOut | Плавное появление/исчезновение |
| slideLeft/Right/Up/Down | Выезд с указанной стороны |

Триггеры: `start` (начало слайда), `end`, `time` (секунды), `marker`, `word`.

---

## 🔊 Script-Audio Sync Tracking

Система отслеживания синхронизации скрипта и аудио.

### Статусы слайда
| Статус | Описание | Индикатор |
|--------|----------|-----------|
| **ready** | Скрипт озвучен, хэши совпадают | 🟢 зелёная точка |
| **outdated** | Скрипт изменён после озвучки | 🟠 оранжевая пульсирующая точка |
| **script-only** | Есть скрипт, но нет аудио | ⚪ серая точка |
| **missing** | Нет скрипта | — |

### Как работает
1. При генерации TTS сохраняется `script_text_hash` (SHA-256 от текста скрипта)
2. При загрузке слайда сравнивается текущий хэш скрипта с сохранённым
3. Если хэши не совпадают → статус `outdated`
4. Fallback для legacy аудио: сравнение `script.updated_at` vs `audio.created_at`

### Pre-render проверка
При нажатии "Render All Languages" проверяются все языки проекта:
- Если есть outdated аудио — показывается предупреждение
- Пользователь может подтвердить рендер или отменить для переозвучки

---

## ✅ Acceptance Criteria

### MVP
- [x] Upload PPTX → корректные PNG слайды
- [x] Редактирование скриптов с autosave
- [x] Generate audio per slide
- [x] Render MP4 без рассинхрона
- [x] Download работает

### v1.1
- [x] Add language + tabs
- [x] Translate with glossary
- [x] TTS для второго языка
- [x] SRT генерация с корректными таймингами
- [x] Music overlay + ducking
- [x] Voice/music gain регуляторы работают
- [x] Смена музыки НЕ триггерит TTS
- [ ] Re-render only changed slides

### v1.2 Canvas Editor
- [x] Canvas Editor с текстовыми слоями
- [x] Плашки (Plate) с настройками стиля
- [x] Изображения из Asset Library
- [x] fontSize корректно применяется (expandHeight по умолчанию)
- [x] Resize текстовых слоёв масштабирует fontSize пропорционально
- [x] Анимации слоёв (fadeIn, slideLeft и др.)
- [x] Мультиязычные текстовые слои с переводами
- [x] Script-Audio sync tracking (outdated status)
- [x] Pre-render проверка для Render All Languages

---

## 🏗 Legacy: rsrohan99/presenter

Используем как adapter layer:
- `adapters/tts.py` — обёртка над ElevenLabs
- `adapters/render.py` — обёртка над FFmpeg

Presenter код не модифицируем, только оборачиваем.

---

## 📜 License

MIT
