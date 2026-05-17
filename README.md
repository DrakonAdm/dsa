# 🚀 DSA — Distributed Segmentation & Analysis

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.1-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.2.0-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-Private-red?style=flat)](#)

> **DSA** — система распределённой сегментации и анализа изображений на базе современных нейросетевых моделей (SAM2, Yolo-World).

---

## ⚡ Быстрый старт

```bash
# 1. Клонируйте репозиторий
git clone -b develop https://github.com/DrakonAdm/dsa.git
cd dsa

# 2. Запустите сервисы
docker-compose up -d
python MainServer/app.py
```

---

## 📦 Установка весов моделей

> ⚠️ **Важно:** Веса моделей **не включены** в репозиторий из-за большого размера.  
> Следуйте инструкции ниже, чтобы скачать и распаковать их вручную.

### 🔹 Модель SAM2 (Grounded-SAM-2)

| Компонент | Ссылка | Размер (архив) | Путь назначения |
|-----------|--------|----------------|-----------------|
| `checkpoints` | [📥 Google Drive](https://drive.google.com/drive/folders/1q04hK6VpeIsCkhbL9eu-4cSLFvXUvrdw?usp=sharing) | ~1.33 GB | `DSA\SAM2\Grounded-SAM-2\checkpoints\` |
| `gdino_checkpoints` | [📥 Google Drive](https://drive.google.com/drive/folders/1q04hK6VpeIsCkhbL9eu-4cSLFvXUvrdw?usp=sharing) | ~1.75 GB | `DSA\SAM2\Grounded-SAM-2\gdino_checkpoints\` |

**Инструкция:**
1. Перейдите по ссылке выше.
2. Скачайте архивы `checkpoints.7z` и `gdino_checkpoints.7z`.
3. Распакуйте их **в корень проекта `DSA`**, следуя структуре:
   ```
   DSA/
   └── SAM2/
       └── Grounded-SAM-2/
           ├── checkpoints/          ← распаковать сюда содержимое checkpoints.7z
           └── gdino_checkpoints/    ← распаковать сюда содержимое gdino_checkpoints.7z
   ```
4. ✅ Убедитесь, что внутри папок появились файлы `.pt`, `.bin` и другие веса.

> 💡 **Если папок `checkpoints/` или `gdino_checkpoints/` не существует** — создайте их вручную перед распаковкой.

---

### 🔹 Модель Yolo-World

| Компонент | Ссылка | Размер (архив) | Путь назначения |
|-----------|--------|----------------|-----------------|
| `weights` | [📥 Google Drive](https://drive.google.com/drive/folders/1as_grh_HjAXnfetv2M7HvxGY69q7Ucck?usp=sharing) | ~2.12 GB | `DSA\YoloWorld\weights\` |

**Инструкция:**
1. Перейдите по ссылке выше.
2. Скачайте архив `weights.7z`.
3. Распакуйте его **в корень проекта `DSA`**, следуя структуре:
   ```
   DSA/
   └── YoloWorld/
       └── weights/    ← распаковать сюда содержимое weights.7z
   ```
4. ✅ Убедитесь, что внутри появились файлы `.pth`, `.bin`, `clip/` и другие артефакты.

> 💡 **Если папки `weights/` не существует** — создайте её вручную перед распаковкой.

---

## 🗂 Структура проекта

```
DSA/
├── MainServer/                 # Backend на FastAPI
│   ├── app.py                  # Точка входа
│   ├── server/                 # Бизнес-логика
│   │   ├── api/                # REST API роутеры
│   │   ├── service/            # Сервисы и репозитории
│   │   └── core/               # Конфигурация, безопасность
│   └── alembic/                # Миграции БД
│
├── SAM2/                       # Сервис сегментации (SAM2 + GroundingDINO)
│   ├── app.py
│   ├── server/
│   └── Grounded-SAM-2/
│       ├── checkpoints/        # ⬅️ ВЕСА: распаковать checkpoints.7z
│       └── gdino_checkpoints/  # ⬅️ ВЕСА: распаковать gdino_checkpoints.7z
│
├── YoloWorld/                  # Сервис детекции (Yolo-World)
│   ├── app.py
│   ├── server/
│   └── weights/                # ⬅️ ВЕСА: распаковать weights.7z
│
├── client/                     # Frontend на React + TypeScript
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── minio/                      # Объектное хранилище (MinIO)
├── docker-compose.yml          # Оркестрация сервисов
├── .gitignore                  # Исключённые файлы (веса, кэш, .env)
└── README.md                   # Файл описания
```

---

## ⚙️ Конфигурация

1. Создайте файл `.env` в корне проекта на основе `.env.example` (если есть):
   ```env
   # Пример .env
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dsa
   MINIO_ENDPOINT=localhost:9000
   MINIO_ACCESS_KEY=minioadmin
   MINIO_SECRET_KEY=minioadmin
   MODEL_WEIGHTS_DIR=D:/Models/DSA_Weights
   ```

2. Для выноса весов на внешний диск (рекомендуется):
   - Установите переменную окружения `MODEL_WEIGHTS_DIR`
   - Обновите пути в `config.py` соответствующих сервисов

---

## 🐳 Запуск через Docker (рекомендуется)

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

> 💡 Убедитесь, что веса моделей уже распакованы **до** запуска контейнеров, либо смонтируйте внешний диск с весами через `volumes` в `docker-compose.yml`.

---

## 🔧 Устранение неполадок

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Убедитесь, что активировали окружение и установили все `requirements.txt` |
| `FileNotFoundError: ...weights...` | Проверьте, что веса распакованы по правильным путям (см. выше) |
| Ошибка подключения к БД | Проверьте `DATABASE_URL` в `.env` и запущен ли PostgreSQL |
| Ошибка авторизации MinIO | Убедитесь, что `MINIO_ACCESS_KEY` и `SECRET_KEY` совпадают в `.env` и `docker-compose.yml` |
| Git видит веса как изменённые | Добавьте пути в `.gitignore`: `YoloWorld/weights/`, `SAM2/**/checkpoints/` |

---

## 📄 Лицензия

Проект является частной разработкой. Использование, копирование и распространение кода без разрешения запрещено.

---

> 💬 **Вопросы?** Создайте [Issue](https://github.com/DrakonAdm/dsa/issues) или свяжитесь с разработчиком.

<details>
<summary>🔧 Для разработчиков: полезные команды</summary>

```bash
# Проверка стиля кода (если настроен)
ruff check .
black --check .

# Запуск тестов
pytest MainServer/tests/

# Генерация миграций
alembic revision --autogenerate -m "description"
alembic upgrade head

# Очистка кэша Python
find . -type d -name __pycache__ -exec rm -r {} +
find . -name "*.pyc" -delete
```
</details>
