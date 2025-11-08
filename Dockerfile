# 1) base image
FROM python:3.12-slim

# 2) workdir inside the container
WORKDIR /app

# 3) system deps (optional but useful for requests, uvicorn, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4) copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) copy the app code
COPY . .

# 6) env
ENV PORT=8000

# 7) run fastapi with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
