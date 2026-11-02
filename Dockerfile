FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PUBLIC_MODE=1

COPY . .
# 照片质检依赖；不装也能启动（会自动降级）
RUN pip install --no-cache-dir pillow numpy

EXPOSE 8080
CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${PORT:-8080}"]
