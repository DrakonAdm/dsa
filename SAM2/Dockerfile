FROM python:3.10-slim

# Отключаем лишние буферы
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Рабочая директория
WORKDIR /app

# Системные зависимости (важно для cmake и сборки .cpp)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements отдельно (для кеша)
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Установка SAM2
WORKDIR /app/Grounded-SAM-2
RUN pip install -e .

# Установка Grounding DINO
WORKDIR /app/Grounded-SAM-2/grounding_dino
RUN pip install --no-build-isolation -e .

# Возвращаемся в корень приложения
WORKDIR /app

# Команда по умолчанию
CMD ["python", "app.py"]