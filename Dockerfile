FROM python:3.11-slim

# ติดตั้ง dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# สร้าง working directory
WORKDIR /app

# คัดลอก requirements ก่อน (เพื่อใช้ Docker cache)
COPY requirements.txt .

# ติดตั้ง Python packages
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมด
COPY . .

# รันบอท
CMD ["python", "main.py"]
