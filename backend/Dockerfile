FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WINEDEBUG=-all \
    WINEARCH=win64 \
    WINEPREFIX=/root/.wine

WORKDIR /app

# Dependências de sistema:
# - build-essential/libpq-dev: compilar psycopg
# - cabextract, p7zip-full, unzip: inspecionar/extrair instaladores
# - wine: necessário para correr o IntuneWinAppUtil.exe original (.NET/Windows)
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    cabextract \
    p7zip-full \
    unzip \
    curl \
    gnupg2 \
    software-properties-common \
    wine \
    wine32:i386 \
    && rm -rf /var/lib/apt/lists/*

RUN winecfg /? >/dev/null 2>&1 || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p /app/storage/downloads /app/storage/packages /app/tools

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
