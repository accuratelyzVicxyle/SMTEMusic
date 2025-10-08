FROM python:3.11-slim

# ติดตั้ง dependencies รวมถึง CA certificates
RUN apt-get update && \
    apt-get install -y ffmpeg ca-certificates && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ตั้งค่า environment variables สำหรับ SSL
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

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
