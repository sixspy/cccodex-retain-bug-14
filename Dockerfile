FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=6500 \
    DATABASE_PATH=/app/instance/retain_lab.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .
RUN mkdir -p /app/instance

EXPOSE 6500

CMD ["python", "run.py"]
