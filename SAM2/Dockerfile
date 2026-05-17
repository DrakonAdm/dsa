FROM python:3.11-slim

# Отключаем лишние буферы
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

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
RUN pip install --no-cache-dir --upgrade pip wheel setuptools
RUN pip install --no-cache-dir \
    --default-timeout=1000 \
    --retries 10 \
    --prefer-binary \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.11.0 torchvision==0.26.0
RUN grep -v '^torch' requirements.txt | grep -v '^torchvision' | grep -v '^torchaudio' > requirements-no-torch.txt && \
    pip install --no-cache-dir \
        --default-timeout=1000 \
        --retries 10 \
        --prefer-binary \
        -r requirements-no-torch.txt

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