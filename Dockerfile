# Gunakan base image Nvidia CUDA dengan dukungan cuDNN untuk Faster-Whisper dan NVENC
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Setup environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    STORAGE_DIR=/app/storage \
    MAX_SOURCE_HEIGHT=1080

# Install dependencies sistem, ffmpeg, dan python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Buat symlink untuk python
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Setup working directory
WORKDIR /app

# Copy requirements dan install dependencies python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy seluruh source code
COPY . .

# Expose port aplikasi
EXPOSE 8000

# Script startup (Otomatis jalankan migrasi DB lalu start Uvicorn)
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
