FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libxcb1 \
    libx11-6 \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей (для кэширования слоя)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего кода (будет переопределено volume при разработке)
COPY . .

# Переменные окружения для Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8085/health || exit 1

# Запуск приложения из /app
CMD ["python", "app.py"]