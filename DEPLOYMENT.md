# 🚀 Video-Creator Production Deployment

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        DigitalOcean VPS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐                                               │
│   │   Caddy     │ ◄── HTTPS :443 / HTTP :80                     │
│   │   (proxy)   │                                               │
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

## Требования к серверу

### Минимальные требования (DigitalOcean Droplet)
- **CPU**: 2 vCPU
- **RAM**: 4 GB (рекомендуется 8 GB для обработки видео)
- **Disk**: 80 GB SSD
- **OS**: Ubuntu 22.04 LTS

### Рекомендуемые требования
- **CPU**: 4 vCPU
- **RAM**: 8 GB
- **Disk**: 160 GB SSD (или DO Spaces для файлов)

## Быстрый старт

### 1. Подготовка сервера

> ⚠️ **Безопасность**: Не используйте подход “pipe-to-shell” (например, `curl → bash`) в production! Это supply-chain риск.
> Вместо этого скачайте скрипт, проверьте его содержимое, затем запустите.

```bash
# Безопасный способ (рекомендуется):
curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/deploy/setup-server.sh -o setup-server.sh
# Проверьте содержимое скрипта:
less setup-server.sh
# Затем запустите:
chmod +x setup-server.sh
./setup-server.sh
```

Или вручную:
```bash
cd /path/to/Video-Creator
chmod +x deploy/*.sh
./deploy/setup-server.sh
```

### 2. Настройка переменных окружения

```bash
# Скопировать пример
cp env.prod.example .env.prod

# Отредактировать с реальными значениями
nano .env.prod
```

**Обязательно измените:**
- `DOMAIN` — ваш домен
- `ADMIN_PASSWORD` — пароль админа
- `SECRET_KEY` — секретный ключ (генерируйте: `openssl rand -hex 32`)
- `POSTGRES_PASSWORD` — пароль БД
- `OPENAI_API_KEY` — ключ OpenAI
- `ELEVENLABS_API_KEY` — ключ ElevenLabs

### 3. Деплой

```bash
./deploy/deploy.sh
```

## Структура файлов

```
Video-Creator/
├── docker-compose.prod.yml    # Production compose
├── env.prod.example           # Пример переменных
├── Caddyfile                  # Конфиг reverse proxy
├── deploy/
│   ├── deploy.sh              # Основной скрипт деплоя
│   ├── setup-server.sh        # Настройка сервера
│   ├── backup.sh              # Бэкап данных
│   └── restore.sh             # Восстановление из бэкапа
├── backend/
│   ├── Dockerfile             # Dev Dockerfile
│   └── Dockerfile.prod        # Production Dockerfile
└── frontend/
    ├── Dockerfile             # Dev Dockerfile
    └── Dockerfile.prod        # Production Dockerfile
```

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| `caddy` | 80, 443 | Reverse proxy + HTTPS |
| `frontend` | 3000 | Next.js приложение |
| `api` | 8000 | FastAPI backend |
| `worker` | - | Celery worker (tts, render, translate) |
| `worker_convert` | - | Celery worker (LibreOffice, concurrency=1) |
| `redis` | 6379 | Брокер задач |
| `db` | 5432 | PostgreSQL |

## Команды

### Деплой
```bash
# Полный деплой (pull + migrate + restart)
./deploy/deploy.sh

# Только перезапуск (без pull)
./deploy/deploy.sh --no-pull

# Посмотреть логи
docker compose -f docker-compose.prod.yml logs -f

# Логи конкретного сервиса
docker compose -f docker-compose.prod.yml logs -f api
```

### Миграции
```bash
# Применить миграции
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Создать новую миграцию
docker compose -f docker-compose.prod.yml exec api alembic revision --autogenerate -m "description"

# Откатить последнюю миграцию
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1
```

### Бэкап и восстановление
```bash
# Создать бэкап
./deploy/backup.sh

# Восстановить из бэкапа
./deploy/restore.sh backups/backup-2024-01-15-120000.tar.gz
```

### Мониторинг
```bash
# Статус сервисов
docker compose -f docker-compose.prod.yml ps

# Использование ресурсов
docker stats

# Очередь задач Celery
docker compose -f docker-compose.prod.yml exec api celery -A app.workers.celery_app inspect active
```

## DNS настройка

Добавьте A-записи в DNS вашего домена:

| Тип | Имя | Значение |
|-----|-----|----------|
| A | @ | YOUR_SERVER_IP |
| A | www | YOUR_SERVER_IP |

## SSL/HTTPS

Caddy автоматически получает и обновляет SSL-сертификаты от Let's Encrypt.

**Требования:**
- Домен должен указывать на сервер
- Порты 80 и 443 должны быть открыты
- Email в `.env.prod` для уведомлений Let's Encrypt

## Переменные окружения (.env.prod)

| Переменная | Описание | Обязательно |
|------------|----------|-------------|
| `DOMAIN` | Ваш домен (example.com) | ✅ |
| `ACME_EMAIL` | Email для Let's Encrypt | ✅ |
| `ENV` | Окружение (prod) | ✅ |
| `ADMIN_PASSWORD` | Пароль админа | ✅ |
| `SECRET_KEY` | JWT секрет | ✅ |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | ✅ |
| `OPENAI_API_KEY` | Ключ OpenAI API | ✅ |
| `ELEVENLABS_API_KEY` | Ключ ElevenLabs API | ✅ |
| `DEFAULT_VOICE_ID` | ID голоса по умолчанию | ❌ |
| `DEFAULT_TTS_MODEL` | Модель TTS | ❌ |

## Обновление приложения

### Автоматически (CI/CD)

При настройке GitHub Actions образы автоматически собираются и пушатся в registry.

```bash
# На сервере достаточно:
./deploy/deploy.sh
```

### Вручную

```bash
# 1. На локальной машине: собрать и запушить образы
docker build -t your-registry/video-creator-api:latest ./backend -f ./backend/Dockerfile.prod
docker build -t your-registry/video-creator-frontend:latest ./frontend -f ./frontend/Dockerfile.prod
docker push your-registry/video-creator-api:latest
docker push your-registry/video-creator-frontend:latest

# 2. На сервере: обновить
cd /opt/video-creator
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Масштабирование

### Горизонтальное масштабирование workers

```bash
# Запустить 3 экземпляра worker
docker compose -f docker-compose.prod.yml up -d --scale worker=3
```

### Вертикальное масштабирование

Измените лимиты в `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 4G
```

## Troubleshooting

### Caddy не получает сертификат

```bash
# Проверить логи Caddy
docker compose -f docker-compose.prod.yml logs caddy

# Убедиться что DNS настроен
dig +short your-domain.com

# Проверить открыты ли порты
nc -zv your-domain.com 80
nc -zv your-domain.com 443
```

### Worker падает

```bash
# Проверить логи
docker compose -f docker-compose.prod.yml logs worker

# Проверить память
free -h

# Перезапустить worker
docker compose -f docker-compose.prod.yml restart worker
```

### База данных недоступна

```bash
# Проверить статус
docker compose -f docker-compose.prod.yml ps db

# Проверить логи
docker compose -f docker-compose.prod.yml logs db

# Проверить подключение
docker compose -f docker-compose.prod.yml exec db psql -U postgres -d presenter -c "SELECT 1"
```

### Очистка места

```bash
# Удалить неиспользуемые образы
docker image prune -a

# Удалить неиспользуемые volumes (ОСТОРОЖНО!)
docker volume prune

# Очистить логи Docker
truncate -s 0 /var/lib/docker/containers/*/*-json.log
```

## Безопасность

### Firewall (UFW)

```bash
# Разрешить только нужные порты
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### Fail2ban

Скрипт `setup-server.sh` автоматически настраивает fail2ban для защиты SSH.

### Обновления

```bash
# Регулярно обновляйте систему
sudo apt update && sudo apt upgrade -y

# Обновляйте Docker образы
docker compose -f docker-compose.prod.yml pull
```

## DigitalOcean Spaces (опционально)

Для хранения файлов вместо локального диска можно использовать DO Spaces (S3-compatible):

```env
# .env.prod
STORAGE_TYPE=s3
S3_ENDPOINT=https://nyc3.digitaloceanspaces.com
S3_BUCKET=your-bucket-name
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
```

> ⚠️ Требуется доработка кода для поддержки S3 storage.

## Мониторинг (опционально)

Для production рекомендуется добавить:

- **Prometheus + Grafana** — метрики
- **Sentry** — отслеживание ошибок
- **Uptime Robot / Better Stack** — мониторинг доступности

---

## Контакты

При проблемах с деплоем создайте issue в репозитории.

