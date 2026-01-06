## STARTUP / Runbook (Video-Creator)

Этот репозиторий содержит **2 независимых контура**:

- **Web‑платформа** (`frontend/` + `backend/` + `Celery` + `Postgres` + `Redis`): загрузка PPTX → конвертация в слайды → редактирование скриптов → перевод/TTS → рендер MP4 + SRT.
- **CLI workflow** (`run.py` + `workflow.py` + `agents/`): генерация презентации из темы/данных и (опционально) экспорт видео с озвучкой.

---

## Быстрый старт (Docker Compose) — рекомендовано

### Предусловия
- **Docker** + **Docker Compose**

### 1) Подготовить переменные окружения Backend

```bash
cp backend/env.example backend/.env
```

Откройте `backend/.env` и заполните минимум:
- `OPENAI_API_KEY`
- `ELEVENLABS_API_KEY`
- (опционально) `ADMIN_PASSWORD`, `SECRET_KEY`

### 2) Собрать и запустить

```bash
docker compose up -d --build
```

Если у вас старая версия Docker Compose:

```bash
docker-compose up -d --build
```

### 3) Открыть сервисы
- **Frontend (UI):** `http://localhost:3000`
- **Backend (Swagger):** `http://localhost:8000/docs`
- **Healthcheck:** `http://localhost:8000/health`
- **Postgres (host):** `localhost:5433` (внутри compose — `db:5432`)
- **Redis (host):** `localhost:6379`

### 4) Остановить

```bash
docker compose down
```

Полная очистка БД (удалит volume Postgres):

```bash
docker compose down -v
```

---

## Локальная разработка (без Docker)

### Предусловия
- **Python 3.11+**
- **Node.js 20+**
- **PostgreSQL 15+**
- **Redis 7+**
- Системные утилиты: **ffmpeg**, **libreoffice** (headless), **poppler-utils**, шрифты (Noto/Inter/Roboto/Open Sans)

> На macOS обычно достаточно `brew install ffmpeg libreoffice poppler redis postgresql@15`.

### Backend (FastAPI)

```bash
cd backend
cp env.example .env
```

Рекомендуемые значения для локального запуска (из `backend/`):
- `DATA_DIR=../data/projects`
- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/presenter`
- `REDIS_URL=redis://localhost:6379/0`

Далее:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Celery worker

В отдельном терминале (из `backend/`):

```bash
source .venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info
```

> Для продакшена конвертацию PPTX лучше выносить в отдельный worker с `--concurrency=1` (LibreOffice не любит параллель).

### Frontend (Next.js)

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev
```

Открыть UI: `http://localhost:3000`.

---

## CLI workflow (`run.py`) — генерация презентации и видео (опционально)

### Предусловия
- **Python 3.11+**
- **ffmpeg/ffprobe**
- Node‑CLI утилиты, которые вызываются из `workflow.py`:
  - `mmdc` (Mermaid CLI)
  - `mdslides`
  - `decktape`

### Установка зависимостей (CLI)

```bash
python -m venv .venv-cli
source .venv-cli/bin/activate
pip install -r requirements.txt
```

Создайте `.env` в корне репозитория:

```env
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
# Опционально (если используете парсинг PDF через LlamaParse):
# LLAMA_CLOUD_API_KEY=...
```

### Запуск

```bash
python run.py "My presentation topic"
python run.py "My presentation topic" --export-video
```

Результаты появятся в `presentations/<topic>/` (HTML/PDF/PNG/MP4).

---

## Troubleshooting

- **Слайды не отображаются в UI**: проверьте `NEXT_PUBLIC_API_URL` и что backend доступен на `http://localhost:8000`. Если backend на другом хосте/порту — обновите `frontend/next.config.js` (images remotePatterns).
- **Конвертация PPTX падает**: проверьте наличие `libreoffice` и права на `DATA_DIR`. Для стабильности — отдельный Celery worker для очереди `convert_queue` с `--concurrency=1`.
- **TTS/Translate возвращают ошибку**: проверьте `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` в `backend/.env` (и `.env` в корне для CLI).


