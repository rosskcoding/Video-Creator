# 📋 Техническая Спецификация: Video-Creator Platform

**Версия:** 1.2.0  
**Дата:** Январь 2026  
**Тип системы:** Веб-приложение для создания мультиязычных видео-презентаций с AI-озвучкой

> 🚀 **Production Ready** — см. раздел [9.2 Production Deployment](#92-production-deployment-digitalocean--vps) и [`DEPLOYMENT.md`](./DEPLOYMENT.md)

---

## 1. Обзор системы

### 1.1 Назначение

Платформа для автоматизированного создания видео-презентаций с мультиязычной озвучкой. Система принимает PowerPoint презентации, конвертирует их в видео с профессиональной озвучкой на нескольких языках, добавляет фоновую музыку и генерирует субтитры.

### 1.2 Ключевые возможности

| # | Функция | Описание |
|---|---------|----------|
| 1 | PPTX → PNG | Конвертация слайдов PowerPoint в изображения |
| 2 | Script Editor | Редактирование сценариев для каждого слайда |
| 3 | Multi-language | Перевод через OpenAI GPT-4o с глоссарием |
| 4 | TTS | Озвучка через ElevenLabs с кэшированием |
| 5 | Audio Mix | Фоновая музыка + ducking + loudness normalization |
| 6 | Export | MP4 видео + SRT субтитры для каждого языка |

### 1.3 Архитектура высокого уровня

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend API    │────▶│   PostgreSQL    │
│   (Next.js)     │     │   (FastAPI)      │     │                 │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐  ┌──────────┐  ┌─────────┐
              │  Redis  │  │  Celery  │  │ FFmpeg  │
              │ (Queue) │  │ (Worker) │  │(Render) │
              └─────────┘  └────┬─────┘  └─────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              ┌───────────┐          ┌─────────────┐
              │ElevenLabs │          │  OpenAI     │
              │   (TTS)   │          │(Translation)│
              └───────────┘          └─────────────┘
```

### 1.4 Контуры (режимы) работы в репозитории

- **Web‑платформа** (`frontend/` + `backend/`): UI (Next.js) + API (FastAPI) + фоновые задачи (Celery/Redis) + БД (PostgreSQL) + файловое хранилище (`DATA_DIR`).
- **CLI workflow** (`run.py`, `workflow.py`, `agents/`): генерация презентаций из темы/данных с помощью LlamaIndex и опциональный экспорт видео/озвучки (ElevenLabs + FFmpeg). Контур не зависит от web‑платформы и может запускаться отдельно.

---

## 2. Технологический стек

### 2.1 Backend

| Технология | Версия | Назначение |
|------------|--------|------------|
| Python | 3.11+ | Основной язык |
| FastAPI | ≥0.109.0 | REST API framework |
| PostgreSQL | 15 | Основная БД |
| SQLAlchemy | ≥2.0.25 | ORM (async) |
| asyncpg | ≥0.29.0 | Async PostgreSQL driver |
| Alembic | ≥1.13.1 | Миграции БД |
| Celery | ≥5.3.6 | Очередь фоновых задач |
| Redis | 7 | Message broker для Celery |
| FFmpeg | latest | Рендер видео, audio mix |
| python-pptx | ≥0.6.23 | Извлечение speaker notes |
| Pillow | ≥10.2.0 | Обработка изображений |

### 2.2 Frontend

| Технология | Версия | Назначение |
|------------|--------|------------|
| Next.js | 14.1.0 | React framework (App Router) |
| React | ^18.2.0 | UI библиотека |
| TypeScript | ^5.3.3 | Типизация |
| Tailwind CSS | ^3.4.1 | Стилизация |
| @tanstack/react-query | ^5.17.19 | Управление серверным состоянием |
| axios | ^1.6.7 | HTTP клиент |
| lucide-react | ^0.321.0 | Иконки |
| react-dropzone | ^14.2.3 | Drag & Drop загрузка файлов |
| sonner | ^1.4.0 | Toast уведомления |

### 2.3 External APIs

| Сервис | Назначение |
|--------|------------|
| ElevenLabs | Text-to-Speech (TTS) |
| OpenAI GPT-4o | Перевод текста |

### 2.4 DevOps

| Технология | Назначение |
|------------|------------|
| Docker | Контейнеризация |
| Docker Compose | Оркестрация сервисов |

---

## 3. Модель данных

### 3.1 ER-диаграмма

```
┌─────────────────┐       ┌───────────────────┐
│    Project      │       │  ProjectVersion   │
├─────────────────┤       ├───────────────────┤
│ id (UUID, PK)   │───┬──▶│ id (UUID, PK)     │
│ name            │   │   │ project_id (FK)   │
│ base_language   │   │   │ version_number    │
│ current_ver_id  │   │   │ pptx_asset_path   │
│ created_at      │   │   │ slides_hash       │
│ updated_at      │   │   │ status            │
└─────────────────┘   │   │ comment           │
        │             │   │ created_at        │
        │             │   └───────────────────┘
        │             │            │
        ▼             │            ▼
┌──────────────────┐  │   ┌───────────────────┐
│ProjectAudioSetts │  │   │      Slide        │
├──────────────────┤  │   ├───────────────────┤
│ project_id (PK)  │  │   │ id (UUID, PK)     │
│ bg_music_enabled │  │   │ project_id (FK)   │
│ music_asset_id   │  │   │ version_id (FK)   │
│ voice_gain_db    │  │   │ slide_index       │
│ music_gain_db    │  │   │ image_path        │
│ ducking_enabled  │  │   │ notes_text        │
│ ducking_strength │  │   │ slide_hash        │
│ target_lufs      │  │   │ created_at        │
└──────────────────┘  │   └───────────────────┘
        │             │            │
        ▼             │            ├────────┬────────┐
┌───────────────────┐ │            ▼        ▼        ▼
│ProjectTranslRules │ │   ┌────────────┐ ┌────────┐ ┌──────────┐
├───────────────────┤ │   │SlideScript │ │SlideAud│ │ RenderJob│
│ project_id (PK)   │ │   ├────────────┤ ├────────┤ ├──────────┤
│ do_not_translate  │ │   │ id (PK)    │ │ id (PK)│ │ id (PK)  │
│ pref_translations │ │   │ slide_id   │ │slide_id│ │project_id│
│ style             │ │   │ lang       │ │ lang   │ │version_id│
│ extra_rules       │ │   │ text       │ │voice_id│ │ lang     │
└───────────────────┘ │   │ source     │ │ path   │ │ job_type │
                      │   │ meta_json  │ │duration│ │ status   │
        ▼             │   │ updated_at │ │ hash   │ │progress  │
┌──────────────────┐  │   └────────────┘ └────────┘ │ output   │
│   AudioAsset     │  │                             │ error    │
├──────────────────┤  │                             │ times    │
│ id (UUID, PK)    │──┘                             └──────────┘
│ project_id (FK)  │
│ type (music)     │
│ file_path        │
│ original_format  │
│ duration_sec     │
└──────────────────┘
```

### 3.2 Описание таблиц

#### Projects
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| name | VARCHAR(255) | Название проекта |
| base_language | VARCHAR(10) | Базовый язык (по умолчанию "en") |
| current_version_id | UUID | Ссылка на текущую версию |
| created_at | TIMESTAMP | Дата создания |
| updated_at | TIMESTAMP | Дата обновления |

#### ProjectVersions
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| project_id | UUID (FK) | Ссылка на проект |
| version_number | INTEGER | Номер версии (автоинкремент в рамках проекта) |
| pptx_asset_path | VARCHAR(500) | Путь к PPTX файлу |
| slides_hash | VARCHAR(64) | SHA256 хэш слайдов |
| status | ENUM | draft / ready / rendering / done / failed |
| comment | TEXT | Комментарий к версии |
| created_at | TIMESTAMP | Дата создания |

#### Slides
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| project_id | UUID (FK) | Ссылка на проект |
| version_id | UUID (FK) | Ссылка на версию |
| slide_index | INTEGER | Порядковый номер (1-based) |
| image_path | VARCHAR(500) | Путь к PNG изображению |
| notes_text | TEXT | Speaker notes из PPTX |
| slide_hash | VARCHAR(64) | Хэш изображения слайда |
| created_at | TIMESTAMP | Дата создания |

#### SlideScripts
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| slide_id | UUID (FK) | Ссылка на слайд |
| lang | VARCHAR(10) | Код языка (en, ru, uk, etc.) |
| text | TEXT | Текст сценария |
| source | ENUM | manual / imported_notes / translated |
| translation_meta_json | JSON | Метаданные перевода |
| updated_at | TIMESTAMP | Дата обновления |

#### SlideAudio
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| slide_id | UUID (FK) | Ссылка на слайд |
| lang | VARCHAR(10) | Код языка |
| provider | VARCHAR(50) | Провайдер TTS (elevenlabs) |
| voice_id | VARCHAR(100) | ID голоса |
| audio_path | VARCHAR(500) | Путь к WAV файлу |
| duration_sec | FLOAT | Длительность в секундах |
| audio_hash | VARCHAR(64) | Хэш для кэширования |
| created_at | TIMESTAMP | Дата создания |

#### AudioAssets
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| project_id | UUID (FK) | Ссылка на проект |
| type | VARCHAR(50) | Тип ассета (music) |
| file_path | VARCHAR(500) | Путь к файлу |
| original_format | VARCHAR(10) | Формат (mp3) |
| duration_sec | FLOAT | Длительность |
| created_at | TIMESTAMP | Дата создания |

#### ProjectAudioSettings
| Поле | Тип | Default | Описание |
|------|-----|---------|----------|
| project_id | UUID (PK) | - | Ссылка на проект |
| background_music_enabled | BOOLEAN | false | Включить фоновую музыку |
| music_asset_id | UUID (FK) | null | Ссылка на музыкальный ассет |
| voice_gain_db | FLOAT | 0.0 | Усиление голоса (dB) |
| music_gain_db | FLOAT | -22.0 | Усиление музыки (dB) |
| ducking_enabled | BOOLEAN | true | Приглушение музыки под голосом |
| ducking_strength | ENUM | default | light / default / strong |
| target_lufs | INTEGER | -14 | Целевая громкость (LUFS) |

#### ProjectTranslationRules
| Поле | Тип | Описание |
|------|-----|----------|
| project_id | UUID (PK) | Ссылка на проект |
| do_not_translate | JSON Array | Термины без перевода ["IFRS", "ESG"] |
| preferred_translations | JSON Array | [{term, lang, translation}] |
| style | ENUM | formal / neutral / friendly |
| extra_rules | TEXT | Дополнительные правила |

#### RenderJobs
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | Первичный ключ |
| project_id | UUID (FK) | Ссылка на проект |
| version_id | UUID (FK) | Ссылка на версию |
| lang | VARCHAR(10) | Язык рендера |
| job_type | ENUM | convert / tts / render / preview |
| status | ENUM | queued / running / done / failed |
| progress_pct | INTEGER | Прогресс (0-100) |
| logs_path | VARCHAR(500) | Путь к логам |
| output_video_path | VARCHAR(500) | Путь к выходному MP4 |
| output_srt_path | VARCHAR(500) | Путь к SRT субтитрам |
| error_message | TEXT | Сообщение об ошибке |
| started_at | TIMESTAMP | Время старта |
| finished_at | TIMESTAMP | Время завершения |

---

## 4. API Спецификация

### 4.1 Базовый URL

```
http://localhost:8000/api
```

### 4.2 Endpoints

#### 4.2.1 Projects

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/projects` | Создать проект |
| GET | `/projects` | Список проектов |
| GET | `/projects/{id}` | Получить проект |
| PATCH | `/projects/{id}` | Обновить проект |
| DELETE | `/projects/{id}` | Удалить проект |
| POST | `/projects/{id}/upload_pptx` | Загрузить PPTX |
| GET | `/projects/{id}/versions` | Список версий |
| POST | `/projects/{id}/versions/{vid}/convert` | Конвертировать PPTX |
| GET | `/projects/{id}/audio_settings` | Получить настройки аудио |
| PUT | `/projects/{id}/audio_settings` | Обновить настройки аудио |
| POST | `/projects/{id}/upload_music` | Загрузить музыку |
| GET | `/projects/{id}/translation_rules` | Получить правила перевода |
| PUT | `/projects/{id}/translation_rules` | Обновить правила перевода |

#### 4.2.2 Slides

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/slides/projects/{pid}/versions/{vid}/slides` | Список слайдов |
| GET | `/slides/{id}` | Получить слайд с скриптами |
| GET | `/slides/{id}/scripts` | Получить скрипты слайда |
| PATCH | `/slides/{id}/scripts/{lang}` | Обновить скрипт |
| POST | `/slides/projects/{pid}/versions/{vid}/languages/add` | Добавить язык |
| POST | `/slides/projects/{pid}/versions/{vid}/import_notes` | Импорт speaker notes |
| POST | `/slides/projects/{pid}/versions/{vid}/translate` | Перевести все слайды |
| POST | `/slides/{id}/tts` | TTS для слайда |
| POST | `/slides/projects/{pid}/versions/{vid}/tts` | TTS для всех слайдов |

#### 4.2.3 Render

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/render/projects/{pid}/versions/{vid}/render` | Рендер для языка |
| POST | `/render/projects/{pid}/versions/{vid}/render_all` | Рендер для всех языков |
| GET | `/render/jobs/{id}` | Статус задачи |
| GET | `/render/projects/{pid}/jobs` | Список задач проекта |
| GET | `/render/projects/{pid}/versions/{vid}/exports` | Список экспортов |
| GET | `/render/projects/{pid}/versions/{vid}/download/{lang}/{file}` | Скачать файл |

#### 4.2.4 Health

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/health` | Проверка здоровья сервиса |

#### 4.2.5 Static Slides (вне `/api`)

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/static/slides/{project_id}/{version_id}/{filename}` | Выдача PNG слайдов (только `001.png`, `002.png`, …) с защитой от path traversal. Используется фронтендом для отображения слайдов. |

### 4.3 Примеры запросов

#### Создание проекта

```http
POST /api/projects
Content-Type: application/json

{
  "name": "Q4 Financial Report",
  "base_language": "en"
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Q4 Financial Report",
  "base_language": "en",
  "current_version_id": null,
  "created_at": "2026-01-06T10:00:00Z",
  "updated_at": "2026-01-06T10:00:00Z"
}
```

#### Загрузка PPTX

```http
POST /api/projects/{project_id}/upload_pptx
Content-Type: multipart/form-data

file: <binary>
comment: "Initial version"
```

**Response:**
```json
{
  "version_id": "660e8400-e29b-41d4-a716-446655440001",
  "version_number": 1,
  "pptx_path": "/data/projects/{project_id}/versions/{version_id}/input.pptx",
  "status": "uploaded",
  "message": "PPTX uploaded. Call /convert to process slides."
}
```

#### Обновление правил перевода

```http
PUT /api/projects/{project_id}/translation_rules
Content-Type: application/json

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

## 5. Celery Tasks (Фоновые задачи)

### 5.1 Список задач

| Task Name | Описание | Retry | Timeout |
|-----------|----------|-------|---------|
| `convert_pptx_task` | PPTX → PNG + extract notes | 1 | 10 мин |
| `tts_slide_task` | TTS для одного слайда | 3 | 3 мин |
| `tts_batch_task` | TTS для всех слайдов версии | 1 | 30 мин |
| `translate_batch_task` | Перевод всех слайдов | 1 | 10 мин |
| `render_language_task` | Рендер видео для языка | 1 | 1 час |

### 5.2 Workflow рендера

```
┌─────────────────────────────────────────────────────────────────┐
│                     render_language_task                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Load slides + audio files                    [0-20%]       │
│                      ↓                                          │
│  2. Build voice timeline (concat + padding)      [20-40%]      │
│                      ↓                                          │
│  3. Mix audio (voice + music + ducking)          [40-60%]      │
│                      ↓                                          │
│  4. Generate SRT subtitles                       [60-70%]      │
│                      ↓                                          │
│  5. Render video (slides + transitions + audio)  [70-100%]     │
│                      ↓                                          │
│  Output: deck_{lang}.mp4 + deck_{lang}.srt                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Адаптеры (External Services)

### 6.1 TTS Adapter (ElevenLabs)

**Файл:** `backend/app/adapters/tts.py`

**Класс:** `TTSAdapter`

| Метод | Описание |
|-------|----------|
| `generate_speech(text, output_path, voice_id, model)` | Генерация речи |
| `compute_audio_hash(text, voice_id, lang, model)` | Хэш для кэширования |
| `check_cache(audio_hash, audio_dir)` | Проверка кэша |

**Кэширование:** `sha256(lang|voice_id|text|model|params_version)`

**Выходной формат:** WAV (PCM 16-bit, 44.1kHz, stereo)

### 6.2 Translation Adapter (OpenAI)

**Файл:** `backend/app/adapters/translate.py`

**Класс:** `TranslateAdapter`

| Метод | Описание |
|-------|----------|
| `translate(text, src, tgt, glossary, style)` | Перевод одного текста |
| `translate_batch(texts, src, tgt, glossary, style)` | Батч-перевод |

**Параметры перевода:**
- `do_not_translate`: Список терминов без перевода
- `preferred_translations`: Словарь предпочтительных переводов
- `style`: formal / neutral / friendly
- `extra_rules`: Дополнительные инструкции

**Model:** `gpt-4o` (temperature=0.3)

### 6.3 Render Adapter (FFmpeg)

**Файл:** `backend/app/adapters/render.py`

**Класс:** `RenderAdapter`

| Метод | Описание |
|-------|----------|
| `render_video_from_slides(slides, audio, output)` | Рендер видео |
| `build_voice_timeline(audio_files, output)` | Сборка voice timeline |
| `mix_audio(voice, music, output, settings)` | Микширование аудио |
| `generate_srt(subtitles, output)` | Генерация субтитров |

**FFmpeg фильтры для ducking:**
```
[voice][music]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=400
```

---

## 7. Константы и настройки

### 7.1 Video Output

| Параметр | Значение | ENV Variable |
|----------|----------|--------------|
| Resolution | 1920×1080 | VIDEO_WIDTH, VIDEO_HEIGHT |
| FPS | 30 | VIDEO_FPS |
| Video Codec | H.264 (libx264) | VIDEO_CODEC |
| Audio Codec | AAC | AUDIO_CODEC |
| Audio Bitrate | 192kbps | AUDIO_BITRATE |

### 7.2 Timing

| Параметр | Значение | ENV Variable |
|----------|----------|--------------|
| Pre-padding | 3.0 sec | PRE_PADDING_SEC |
| Post-padding | 3.0 sec | POST_PADDING_SEC |
| First slide hold | 1.0 sec | FIRST_SLIDE_HOLD_SEC |
| Last slide hold | 1.0 sec | LAST_SLIDE_HOLD_SEC |
| Transition type | fade | TRANSITION_TYPE |
| Transition duration | 0.5 sec | TRANSITION_DURATION_SEC |

### 7.3 Audio Mix

| Параметр | Значение | ENV Variable |
|----------|----------|--------------|
| Target loudness | -14 LUFS | TARGET_LUFS |
| Voice gain | 0 dB | DEFAULT_VOICE_GAIN_DB |
| Music gain | -22 dB | DEFAULT_MUSIC_GAIN_DB |
| Ducking | enabled | DUCKING_ENABLED |
| Ducking strength | default | DUCKING_STRENGTH |

### 7.4 Ducking Parameters

| Strength | Threshold | Ratio | Attack | Release |
|----------|-----------|-------|--------|---------|
| light | 0.03 | 3 | 100ms | 500ms |
| default | 0.02 | 6 | 50ms | 400ms |
| strong | 0.01 | 10 | 20ms | 300ms |

---

## 8. Структура файловой системы

```
/data/projects/
└── {project_id}/
    ├── music/
    │   └── corporate.mp3
    └── versions/
        └── {version_id}/
            ├── input.pptx
            ├── slides/
            │   ├── 001.png
            │   ├── 002.png
            │   └── ...
            ├── audio/
            │   ├── en/
            │   │   ├── slide_001.wav
            │   │   ├── slide_002.wav
            │   │   └── ...
            │   └── ru/
            │       ├── slide_001.wav
            │       └── ...
            ├── timelines/
            │   ├── voice_timeline_en.wav
            │   ├── voice_timeline_ru.wav
            │   ├── final_audio_en.wav
            │   └── final_audio_ru.wav
            ├── clips/                    # Временные файлы
            │   ├── clip_000.mp4
            │   └── ...
            └── exports/
                ├── en/
                │   ├── deck_en.mp4
                │   └── deck_en.srt
                └── ru/
                    ├── deck_ru.mp4
                    └── deck_ru.srt
```

---

## 9. Docker Deployment

### 9.1 Development (Local)

#### Services

| Service | Port | Описание |
|---------|------|----------|
| db | 5433 → 5432 | PostgreSQL 15 (host → container) |
| redis | 6379 | Redis 7 |
| backend | 8000 | FastAPI |
| celery_worker | - | Celery Worker (tts, render, translate) |
| celery_worker_convert | - | Celery Worker (LibreOffice, concurrency=1) |
| frontend | 3000 | Next.js |

#### Volumes

| Volume | Назначение |
|--------|------------|
| postgres_data | Данные PostgreSQL |
| ./data | Файлы проектов |

#### Environment Variables (Dev)

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/presenter

# Redis
REDIS_URL=redis://redis:6379/0

# APIs
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...

# Storage
DATA_DIR=/data/projects

# Auth
ADMIN_PASSWORD=admin
SECRET_KEY=change-me-in-production

# TTS
DEFAULT_VOICE_ID=1SM7GgM6IMuvQlz2BwM3
DEFAULT_TTS_MODEL=eleven_flash_v2_5

# Translation
TRANSLATION_MODEL=gpt-4o
```

### 9.2 Production Deployment (DigitalOcean / VPS)

> 📖 Подробная документация: [`DEPLOYMENT.md`](./DEPLOYMENT.md)

#### Архитектура Production

```
┌─────────────────────────────────────────────────────────────────┐
│                        DigitalOcean VPS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐                                               │
│   │   Caddy     │ ◄── HTTPS :443 / HTTP :80                     │
│   │   (proxy)   │     Auto SSL (Let's Encrypt)                  │
│   └──────┬──────┘                                               │
│          │                                                      │
│   ┌──────┴──────────────────────────┐                           │
│   │                                 │                           │
│   ▼                                 ▼                           │
│ ┌───────────┐                 ┌───────────┐                     │
│ │ Frontend  │                 │    API    │                     │
│ │ (Next.js) │                 │ (FastAPI) │                     │
│ │  :3000    │                 │  :8000    │                     │
│ └───────────┘                 └─────┬─────┘                     │
│                                     │                           │
│                      ┌──────────────┼──────────────┐            │
│                      │              │              │            │
│                      ▼              ▼              ▼            │
│               ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│               │  Redis   │   │ Postgres │   │  Worker  │        │
│               │  :6379   │   │  :5432   │   │ (Celery) │        │
│               └──────────┘   └──────────┘   └──────────┘        │
│                                     │                           │
│                                     ▼                           │
│                            ┌────────────────┐                   │
│                            │  Data Volume   │                   │
│                            │ /data/projects │                   │
│                            └────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Production Services

| Service | Порт | Описание |
|---------|------|----------|
| caddy | 80, 443 | Reverse proxy + auto HTTPS |
| frontend | 3000 (internal) | Next.js (standalone) |
| api | 8000 (internal) | FastAPI (2 workers) |
| worker | - | Celery (tts, render, translate, concurrency=2) |
| worker_convert | - | Celery (LibreOffice, concurrency=1) |
| redis | 6379 (internal) | Брокер задач + persistence |
| db | 5432 (internal) | PostgreSQL |
| migrate | one-off | Alembic миграции |

#### Production Volumes

| Volume | Назначение |
|--------|------------|
| video-creator-postgres | Данные PostgreSQL |
| video-creator-redis | Redis persistence |
| video-creator-uploads | Файлы проектов (/data/projects) |
| video-creator-caddy-data | SSL сертификаты |
| video-creator-caddy-config | Caddy конфиг |

#### Требования к серверу

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 80 GB SSD | 160 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

#### Файлы деплоя

```
Video-Creator/
├── docker-compose.prod.yml    # Production compose
├── Caddyfile                  # Reverse proxy config
├── env.prod.example           # Шаблон переменных
├── DEPLOYMENT.md              # Документация деплоя
├── backend/
│   ├── Dockerfile             # Dev image
│   └── Dockerfile.prod        # Production image (multi-stage)
├── frontend/
│   ├── Dockerfile             # Dev image
│   └── Dockerfile.prod        # Production image (standalone)
├── deploy/
│   ├── setup-server.sh        # Настройка сервера
│   ├── deploy.sh              # Основной скрипт деплоя
│   ├── backup.sh              # Бэкап БД + файлов
│   └── restore.sh             # Восстановление
└── .github/
    └── workflows/
        └── deploy.yml         # CI/CD (GitHub Actions)
```

#### Быстрый старт

```bash
# 1. На сервере: настройка
./deploy/setup-server.sh

# 2. Конфигурация
cp env.prod.example .env.prod
nano .env.prod  # Заполнить секреты

# 3. Деплой
./deploy/deploy.sh --build
```

#### Environment Variables (Production)

```env
# Domain & SSL
DOMAIN=example.com
ACME_EMAIL=admin@example.com

# Environment
ENV=prod

# Security (ОБЯЗАТЕЛЬНО ИЗМЕНИТЬ!)
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=your-db-password

# APIs
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...

# Optional
DEFAULT_VOICE_ID=1SM7GgM6IMuvQlz2BwM3
DEFAULT_TTS_MODEL=eleven_flash_v2_5
TRANSLATION_MODEL=gpt-4o
```

#### CI/CD (GitHub Actions)

При push в `main`:
1. Собираются Docker образы (multi-stage build)
2. Push в GitHub Container Registry (ghcr.io)
3. SSH на сервер → pull → migrate → restart

**Secrets для GitHub:**
- `SSH_HOST` — IP сервера
- `SSH_USER` — пользователь (deploy)
- `SSH_PRIVATE_KEY` — SSH ключ
- `DOMAIN` — домен для build arg

---

## 10. Безопасность

### 10.1 Аутентификация

- **Single-tenant**: один администратор (`admin` / `ADMIN_PASSWORD`).
- **Текущее состояние (v1)**: `/api/auth/*` использует **HTTP Basic**. `POST /api/auth/login` возвращает упрощённый token‑string (без JWT).
- **Важно**: основные API‑роуты в текущей версии **не защищены авторизацией** (TODO: включить JWT и требование токена на приватных эндпоинтах).

### 10.2 CORS

Разрешённые origins:
- `http://localhost:3000`
- `http://127.0.0.1:3000`

### 10.3 File Upload

- PPTX: `.pptx` / `.ppt` (**лимит 100 MB**)
- Music: только `.mp3` (**лимит 50 MB**)
- Upload пишется на диск потоково (chunked), чтобы не держать файл целиком в памяти.

---

## 11. Frontend Архитектура

### 11.1 Структура страниц (App Router)

```
/src/app/
├── layout.tsx            # Root layout
├── page.tsx              # Home / Projects list
├── globals.css           # Global styles
├── providers.tsx         # React Query provider
├── admin/
│   ├── page.tsx          # Admin dashboard
│   └── jobs/
│       └── page.tsx      # Jobs monitoring
└── projects/
    └── [id]/
        ├── page.tsx      # Project editor
        └── settings/
            └── page.tsx  # Project settings
```

### 11.2 Компоненты

```
/src/components/
├── CreateProjectModal.tsx
├── layout/
│   └── Sidebar.tsx
└── ui/
    ├── Badge.tsx
    ├── Button.tsx
    ├── Card.tsx
    ├── Dialog.tsx
    ├── Input.tsx
    ├── Progress.tsx
    ├── Select.tsx
    ├── Slider.tsx
    ├── Switch.tsx
    ├── Tabs.tsx
    └── Textarea.tsx
```

### 11.3 State Management

- **React Query**: серверное состояние (projects, slides, jobs)
- **React useState/useReducer**: локальное состояние UI

---

## 12. Testing

### 12.1 Backend Tests

**Framework:** pytest + pytest-asyncio

**Структура:**
```
/backend/tests/
├── conftest.py           # Fixtures
├── test_main.py          # App tests
├── test_models.py        # Model tests
├── test_api/
│   ├── test_projects.py
│   ├── test_slides.py
│   └── test_render.py
└── test_adapters/
    ├── test_pptx_converter.py
    ├── test_translate.py
    └── test_tts.py
```

**Запуск:**
```bash
cd backend
pytest -v --cov=app
```

### 12.2 Test Database

SQLite in-memory для тестов (aiosqlite)

---

## 13. Acceptance Criteria

### 13.1 MVP

- [ ] Upload PPTX → корректные PNG слайды
- [ ] Редактирование скриптов с autosave
- [ ] Generate audio per slide
- [ ] Render MP4 без рассинхрона
- [ ] Download работает

### 13.2 v1.1

- [ ] Add language + tabs
- [ ] Translate with glossary
- [ ] TTS для второго языка
- [ ] SRT генерация с корректными таймингами
- [ ] Music overlay + ducking
- [ ] Voice/music gain регуляторы работают
- [ ] Смена музыки НЕ триггерит TTS
- [ ] Re-render only changed slides

---

## 14. Известные ограничения

| Ограничение | Описание |
|-------------|----------|
| Single-tenant | Один администратор, без multi-user |
| Auth не включён на API | Есть `/api/auth/*`, но остальные эндпоинты не требуют авторизацию (v1) |
| Синхронный Celery | `run_async()` wrapper для async кода |
| Нет WebSocket | Polling для статуса задач |
| Нет превью | Нет real-time preview до рендера |
| Локальное хранилище | Файлы на диске, не S3 (готово к миграции на DO Spaces) |
| LibreOffice concurrency | Конвертация PPTX только в 1 поток (race condition при параллельном запуске) |

---

## 15. Roadmap (Планируемые улучшения)

### v1.2
- [x] Production deployment (Docker Compose + Caddy)
- [x] CI/CD pipeline (GitHub Actions)
- [x] Backup/restore scripts
- [ ] WebSocket для real-time статуса
- [ ] Превью слайда с аудио
- [ ] Выбор голоса ElevenLabs из UI

### v2.0
- [ ] Multi-tenant с ролями
- [ ] S3/DO Spaces storage adapter
- [ ] Streaming рендер
- [ ] Custom transitions
- [ ] Video backgrounds
- [ ] Horizontal scaling (Kubernetes)

---

## 16. Приложения

### A. Зависимости системы

**Backend (apt-get):**
```bash
apt-get install -y \
    ffmpeg \
    libreoffice \
    fonts-inter \
    fonts-roboto \
    fonts-open-sans \
    fonts-noto
```

### B. Полезные команды

```bash
# === Development ===
# Запуск
docker-compose up -d

# Логи Celery
docker-compose logs -f celery_worker

# Подключение к БД
docker-compose exec db psql -U postgres -d presenter

# Ручной запуск миграций
docker-compose exec backend alembic upgrade head

# === Production ===
# Деплой
./deploy/deploy.sh

# Логи
docker compose -f docker-compose.prod.yml logs -f

# Бэкап
./deploy/backup.sh

# Восстановление
./deploy/restore.sh backups/backup-2024-01-15.tar.gz

# Статус сервисов
docker compose -f docker-compose.prod.yml ps

# Масштабирование workers
docker compose -f docker-compose.prod.yml up -d --scale worker=3
```

### C. Контакты и ресурсы

- **ElevenLabs API:** https://elevenlabs.io/docs
- **OpenAI API:** https://platform.openai.com/docs
- **FFmpeg Filters:** https://ffmpeg.org/ffmpeg-filters.html

---

*Документ создан автоматически на основе анализа кодовой базы.*

