# Video-Creator Test Matrix

Полная матрица тестов и аудитов для Video-Creator.

## Обзор

| Категория | Кол-во тестов | Файл |
|-----------|---------------|------|
| 0) Reachability (UI-входы) | 9 | `frontend/e2e/tests/reachability.spec.ts` |
| 1) Flow (сквозные сценарии) | 20 | `backend/tests/test_audit/test_flow_audit.py`, `frontend/e2e/tests/flow-audit.spec.ts` |
| 2) State Machine (статусы) | 12 | `backend/tests/test_audit/test_state_machine_audit.py` |
| 3) Data Integrity (целостность) | 12 | `backend/tests/test_audit/test_data_integrity_audit.py` |
| 4) Resilience (отказоустойчивость) | 10 | `backend/tests/test_audit/test_resilience_audit.py` |
| 5) Performance (производительность) | 10 | `backend/tests/test_audit/test_performance_audit.py` |
| 6) Security (безопасность) | 15 | `backend/tests/test_audit/test_security_audit.py` |
| 7) UX (понятность) | 13 | `frontend/e2e/tests/ux-audit.spec.ts` |
| 8) Observability (наблюдаемость) | 10 | `backend/tests/test_audit/test_observability_audit.py` |
| 9) Regression (регрессия) | 10 | `backend/tests/test_audit/test_regression_audit.py` |

---

## 0) Reachability Audit (UI-входы)

**Цель:** Каждая заявленная фича имеет видимый вход из UI.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| R-01.1 | Кнопка создания проекта | Открыть Home | Кнопка "Create Project" видна | Скриншот |
| R-01.2 | Список проектов | Открыть Home | Проекты или empty state видны | Скриншот |
| R-01.3 | Workspace доступен | Проверить навигацию | Ссылка на Workspace видна | Скриншот |
| R-01.4 | Admin доступен | Проверить навигацию | Ссылка на Admin/Jobs видна | Скриншот |
| R-01.5 | Help доступен | Проверить навигацию | Ссылка на Help видна | Скриншот |
| R-02.1 | Home доступна | GET / | Страница загружается | HTTP 200 |
| R-02.2 | Workspace за ≤2 клика | Home → Workspace | URL /workspace | Navigation path |
| R-02.3 | Admin за ≤2 клика | Home → Admin | URL /admin/* | Navigation path |
| R-02.4 | Проект за ≤2 клика | Home → Project | URL /projects/* | Navigation path |

---

## 1) Flow Audit (сквозные сценарии)

**Цель:** Ключевые пользовательские пути проходят end-to-end.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| F-01 | Новый проект → PPTX → импорт | Создать → Upload → Convert | Слайды появились, порядок корректен | Список слайдов + лог |
| F-02 | Speaker notes импорт | PPTX с notes → Import | Notes = скрипты | До/после сравнение |
| F-03 | Загрузка изображений | Drag&drop PNG/JPG/WebP | Слайды созданы | Метаданные |
| F-04 | Скрипт → автосейв | Изменить текст → F5 | Текст сохранён | Network request |
| F-05 | Reorder слайдов | Drag&drop 5 слайдов | Порядок сохранён | До/после список |
| F-06 | Добавить/удалить слайд | Add → Delete | Индексы обновлены | Список слайдов |
| F-07 | TTS генерация | Скрипт → Generate | Аудио создано | Status + duration |
| F-08 | Перегенерация TTS | Изменить текст → Regenerate | Новый asset ID | Timestamp аудио |
| F-09 | Фоновая музыка | Upload MP3 → Enable | Музыка лупится | Preview audio |
| F-10 | Рендер видео | Render → Done | Видео соответствует | Download URL |

### E2E Flow Tests (Playwright)

| ID | Тест | Шаги | Ожидаемый результат |
|----|------|------|---------------------|
| F-E2E-01 | Create project | UI flow | Проект создан, redirect |
| F-E2E-02 | Project persists | Create → Reload | Проект на месте |
| F-E2E-03 | Script edit persists | Edit → Reload | Текст сохранён |
| F-E2E-04 | Navigate slides | Click slides | Слайд меняется |
| F-E2E-05 | Generation controls | Open project | Кнопка Generate видна |
| F-E2E-06 | Render controls | Open project | Кнопка Render видна |
| F-E2E-07 | Project settings | Project → Settings | Страница настроек |
| F-E2E-08 | Workspace exports | /workspace | Экспорты видны |
| F-E2E-09 | Download links | /workspace | Кнопки скачивания активны |
| F-E2E-10 | Jobs status | /admin/jobs | Статусы видны |

---

## 2) State Machine Audit (статусы)

**Цель:** Генерация предсказуемо живёт в статусах.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| S-01.1 | Начальный статус | Create job | status=queued | Job ID + status |
| S-01.2 | Переход в running | Worker pickup | status=running | Timestamp |
| S-01.3 | Завершение | Done | status=done, 100% | Download URLs |
| S-01.4 | Progress updates | During processing | 0→20→40→...→100 | UI progress |
| S-02.1 | Ошибка TTS | Error condition | status=failed + message | Error code |
| S-02.2 | Нет вечного processing | Error | finished_at != null | Timestamp |
| S-03.1 | Retry создаёт новый job | Retry failed | Новый job_id | Job count |
| S-03.2 | Retry идемпотентен | 3x retry | Нет дубликатов | Asset count |
| S-04.1 | Cancel queued | Cancel | status=failed | revoke called |
| S-04.2 | Cancel running | Cancel | task terminated | SIGTERM sent |
| S-04.3 | Cannot cancel done | Cancel done | HTTP 400 | Error message |
| S-04.4 | Cancel all | Cancel project | All jobs cancelled | Count |

---

## 3) Data Integrity Audit (целостность)

**Цель:** Связи "слайд ↔ скрипт ↔ аудио" остаются корректными.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| D-01.1 | Reorder + аудио | Reorder после TTS | Аудио у своего слайда | Duration check |
| D-01.2 | Reorder + скрипт | Reorder | Скрипт у своего слайда | Text check |
| D-02.1 | Delete → удалить аудио | Delete slide with audio | Audio cascade deleted | DB count |
| D-02.2 | Delete → удалить скрипты | Delete slide | Scripts cascade | DB count |
| D-02.3 | Нет сирот | Delete | Нет orphan assets | Asset query |
| D-03.1 | Last write wins | 2 tabs edit | Последний сохранён | Text check |
| D-03.2 | Concurrent safe | Rapid updates | Нет corruption | Data integrity |
| D-04.1 | Final content | Rapid typing | Последний текст сохранён | Text check |
| D-04.2 | Update timestamp | Edit | updated_at изменился | Timestamp |

---

## 4) Resilience / Failure Audit (отказоустойчивость)

**Цель:** Ошибки не ломают проект.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| E-01.1 | Partial save OK | Save request | 200 OK | Response |
| E-01.2 | Proper error codes | Invalid request | 4xx/5xx | HTTP status |
| E-02.1 | Empty file rejected | Upload empty | 400 | Error message |
| E-02.2 | Corrupted handled | Upload corrupt | No crash | Status |
| E-02.3 | Oversized rejected | Upload >limit | 413 | Error message |
| E-02.4 | Invalid type rejected | Upload .exe | 400 | Error message |
| E-03.1 | Stuck job cancellable | Cancel stuck | status=failed | Job status |
| E-03.2 | Failed job retryable | Retry | New job queued | Job ID |
| E-03.3 | Failed jobs visible | List jobs | Shows failed | Job list |

---

## 5) Performance Audit (производительность)

**Цель:** Предсказуемо работает на больших входах.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| P-01.1 | 50 слайдов | List slides | < 2 сек | Time |
| P-01.2 | 100 слайдов | List slides | < 5 сек | Time |
| P-01.3 | Single slide O(1) | Get slide | < 0.5 сек | Time |
| P-02.1 | 10K chars скрипт | Save | 200 OK | Response |
| P-02.2 | Batch TTS | Queue 20 slides | < 1 сек queue | Time |
| P-03.1 | 20 проектов | List projects | < 2 сек | Time |
| P-03.2 | Parallel jobs | 5 languages | All queued | Job count |
| P-03.3 | Job list filtered | Filter by status | < 1 сек | Time |
| P-04.1 | Pagination | Jobs limit=5 | ≤5 results | Count |
| P-04.2 | Health check | GET /health | < 100ms | Time |

---

## 6) Security Audit (безопасность)

**Цель:** Без критических дыр безопасности.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| SEC-01.1 | 404 на несуществующий | GET /projects/{fake} | 404 | Response |
| SEC-01.2 | Invalid UUID | GET /projects/xyz | 422 | Response |
| SEC-01.3 | SQL injection safe | Name с SQL | Нет выполнения | DB intact |
| SEC-02.1 | File whitelist | Upload .exe | 400 | Response |
| SEC-02.2 | Extension validated | Fake MIME | 400 | Response |
| SEC-02.3 | Path traversal blocked | ../../../etc | Safe | No access |
| SEC-02.4 | Music type restricted | Upload .wav | 400 | Response |
| SEC-03.1 | No API keys in response | GET endpoints | Нет ключей | Response text |
| SEC-03.2 | Errors don't leak secrets | Error responses | Нет секретов | Response |
| SEC-03.3 | No internal paths | Responses | Нет /data/ | Response |
| SEC-04.1 | XSS sanitized | Name с <script> | Safe | Stored/returned |
| SEC-04.2 | Language validated | Invalid lang | 400/422 | Response |
| SEC-04.3 | Auth required | No auth | 401/403 | Response |
| SEC-04.4 | Invalid auth | Wrong creds | 401/403 | Response |

---

## 7) UX Audit (понятность)

**Цель:** Пользователю ясно, что делать дальше.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| UX-01 | Empty projects | Open home | Helpful message | Screenshot |
| UX-02 | Empty workspace | Open workspace | Guidance shown | Screenshot |
| UX-03 | Empty jobs | Open admin | Status shown | Screenshot |
| UX-04 | Loading states | Click action | Loading indicator | Screenshot |
| UX-05 | Validation errors | Submit empty | Error shown | Screenshot |
| UX-06 | Success feedback | Create project | Confirmation | Toast/redirect |
| UX-07 | Delete confirmation | Delete | Dialog shown | Screenshot |
| UX-08 | Cancel confirmation | Cancel job | Feedback | UI state |
| UX-09 | Current page highlight | Navigate | Active link | Screenshot |
| UX-10 | Back navigation | Nested page | Can go back | Navigation |
| UX-11 | Page titles | Each page | Relevant title | Title check |
| UX-12 | 404 friendly | /nonexistent | Helpful page | Screenshot |
| UX-13 | Network error | Offline | User-friendly | Error message |

---

## 8) Compatibility Audit (браузеры)

**Цель:** Работает во всех основных браузерах.

| ID | Тест | Браузер | Проверки |
|----|------|---------|----------|
| C-01.1 | Chrome | Desktop Chrome | Editor, drag&drop, audio |
| C-01.2 | Firefox | Desktop Firefox | Editor, drag&drop, audio |
| C-01.3 | Safari | Desktop Safari | Editor, drag&drop, audio |
| C-02.1 | Mobile Chrome | Pixel 5 | Basic navigation |
| C-02.2 | Mobile Safari | iPhone 12 | Basic navigation |

---

## 9) Observability Audit (наблюдаемость)

**Цель:** Любой фейл можно расследовать за минуты.

| ID | Тест | Шаги | Ожидаемый результат | Доказательство |
|----|------|------|---------------------|----------------|
| O-01.1 | Job has unique ID | Create jobs | Different UUIDs | Job IDs |
| O-01.2 | Job ID in status | GET /jobs/{id} | ID in response | JSON |
| O-01.3 | Error has context | Failed job | Error + job_id | Response |
| O-02.1 | 404 clear | Not found | "not found" message | Response |
| O-02.2 | Validation clear | Invalid input | Field mentioned | Response |
| O-02.3 | Actionable errors | Failed jobs | "please try" type | Message |
| O-03.1 | Timing tracked | Job lifecycle | started_at, finished_at | Timestamps |
| O-03.2 | Progress tracked | Running job | 0-100% | progress_pct |
| O-03.3 | All statuses visible | Admin list | All statuses shown | Job list |
| O-03.4 | Duration calculable | Done job | Both timestamps | Math |

---

## 10) Regression / Golden Tests

**Цель:** Результаты импорта/рендера стабильны между версиями.

| ID | Тест | Входные данные | Ожидаемый результат |
|----|------|----------------|---------------------|
| G-01.1 | Simple PPTX | 3 slides | 3 slides imported |
| G-01.2 | Speaker notes | Notes on each | Notes = scripts |
| G-01.3 | Slide order | Numbered slides | Deterministic order |
| G-02.1 | File hash consistent | Same file | Same hash |
| G-02.2 | Different hash | Different files | Different hashes |
| G-03.1 | Audio hash deterministic | Same params | Same hash |
| G-03.2 | Audio hash changes | Different text | Different hash |
| G-04.1 | Project response | GET project | Required fields |
| G-04.2 | Job response | GET job | Required fields |
| G-04.3 | Slide response | GET slide | Required fields |

---

## Запуск тестов

### Backend (pytest)

```bash
cd backend

# Все аудит-тесты
pytest tests/test_audit/ -v

# Конкретная категория
pytest tests/test_audit/test_flow_audit.py -v
pytest tests/test_audit/test_security_audit.py -v

# С coverage
pytest tests/test_audit/ --cov=app --cov-report=html
```

### Frontend E2E (Playwright)

```bash
cd frontend

# Установка Playwright
npx playwright install

# Все E2E тесты
npx playwright test --config=e2e/playwright.config.ts

# Конкретная категория
npx playwright test e2e/tests/reachability.spec.ts
npx playwright test e2e/tests/ux-audit.spec.ts

# С UI (visual)
npx playwright test --ui

# Отчёт
npx playwright show-report
```

### Все тесты

```bash
# Backend
cd backend && pytest tests/ -v

# Frontend unit tests
cd frontend && npm test

# Frontend E2E
cd frontend && npx playwright test
```

---

## Отчётность

После запуска тестов формируется отчёт:

| Колонка | Описание |
|---------|----------|
| ID | Уникальный идентификатор теста |
| PASS/PARTIAL/FAIL | Статус прохождения |
| Причина | При FAIL - описание проблемы |
| Доказательство | URL скриншота/видео/лога |

### Пример отчёта

```
| ID       | Status  | Причина                    | Доказательство           |
|----------|---------|----------------------------|--------------------------|
| F-01     | PASS    | -                          | screenshot_f01.png       |
| F-02     | PASS    | -                          | network_log.json         |
| S-02.1   | PARTIAL | Message неинформативен     | error_response.json      |
| SEC-01.3 | PASS    | -                          | db_query_log.txt         |
| UX-07    | FAIL    | Нет confirm dialog         | screenshot_delete.png    |
```

---

## Приоритеты тестирования

1. **Critical (P0)**: Security (SEC-*), Data Integrity (D-*)
2. **High (P1)**: Flow (F-*), State Machine (S-*)
3. **Medium (P2)**: Resilience (E-*), Performance (P-*)
4. **Low (P3)**: UX (*UX-*), Observability (O-*)

---

## Добавление новых тестов

1. Определить категорию (Flow, Security, etc.)
2. Присвоить ID по шаблону: `{CATEGORY}-{NUMBER}`
3. Добавить в соответствующий файл
4. Обновить эту матрицу
5. Добавить в CI/CD pipeline

