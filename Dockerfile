# --- STAGE 1: Build the Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy frontend source and compile the build
COPY frontend/ ./
RUN npm run build

# --- STAGE 2: Set up the Python Backend ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY . .

# Copy the compiled static frontend files from Stage 1 into the backend location
# (Change "/app/frontend/dist" if your Vite config builds to a different directory like "/app/frontend/static")
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port and start FastAPI using the dynamic Railway port
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend:app --host 0.0.0.0 --port ${PORT}"]
