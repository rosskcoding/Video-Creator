# 🎬 Presentation → Multilingual Voiceover Video Platform

> Веб-приложение для создания мультиязычных видео-презентаций с озвучкой на базе rsrohan99/presenter

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
id, project_id, version_id, slide_index, image_path, notes_text, slide_hash, created_at
```

### SlideScripts
```
id, slide_id, lang, text, source (manual|imported_notes|translated), translation_meta_json, updated_at
```

### SlideAudio
```
id, slide_id, lang, voice_id, audio_path, duration_sec, audio_hash, created_at
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

## ✅ Acceptance Criteria

### MVP
- [ ] Upload PPTX → корректные PNG слайды
- [ ] Редактирование скриптов с autosave
- [ ] Generate audio per slide
- [ ] Render MP4 без рассинхрона
- [ ] Download работает

### v1.1
- [ ] Add language + tabs
- [ ] Translate with glossary
- [ ] TTS для второго языка
- [ ] SRT генерация с корректными таймингами
- [ ] Music overlay + ducking
- [ ] Voice/music gain регуляторы работают
- [ ] Смена музыки НЕ триггерит TTS
- [ ] Re-render only changed slides

---

## 🏗 Legacy: rsrohan99/presenter

Используем как adapter layer:
- `adapters/tts.py` — обёртка над ElevenLabs
- `adapters/render.py` — обёртка над FFmpeg

Presenter код не модифицируем, только оборачиваем.

---

## 📜 License

MIT
