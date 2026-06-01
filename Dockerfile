FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    libpq-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector/ ./collector/
COPY data_mos_export_2855.py data_mos_export_2941.py \
     data_mos_export_62461.py data_mos_export_62501.py \
     data_mos_export_1498.py data_mos_export_1500.py \
     data_mos_export_2386.py data_mos_export_62441.py .

CMD ["python", "-m", "collector.scheduler"]
