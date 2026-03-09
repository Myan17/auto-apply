FROM python:3.11-slim

# System deps for Playwright + PDF libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libpangocairo-1.0-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir openai

# Install Playwright + Chromium
RUN playwright install chromium && playwright install-deps chromium

# Copy source
COPY src/ src/
COPY config/ config/

# Entrypoint
ENTRYPOINT ["auto-apply"]
CMD ["--help"]
