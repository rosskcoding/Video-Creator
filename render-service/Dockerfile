# Render Service - Puppeteer-based video renderer
#
# Multi-stage build:
# - builder: installs dev deps and compiles TS -> dist/
# - runtime: installs system deps (chromium + ffmpeg), installs prod deps, runs node dist/index.js

FROM node:20-slim AS builder

WORKDIR /app

# Prevent Puppeteer from downloading Chromium during npm install
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src

RUN npm run build


FROM node:20-slim AS runtime

# Install dependencies for Puppeteer + FFmpeg + Fonts
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-roboto \
    fonts-open-sans \
    fonts-lato \
    fonts-dejavu \
    fonts-freefont-ttf \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    ffmpeg \
    wget \
    unzip \
    fontconfig \
    ca-certificates \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Download and install Inter font (not available in Debian repos)
# Using Inter v4.0 static TTF fonts
RUN mkdir -p /usr/share/fonts/truetype/inter && \
    wget -q -O /tmp/inter.zip "https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip" && \
    unzip -q /tmp/inter.zip -d /tmp/inter && \
    find /tmp/inter -type f \( -name "*.ttf" -o -name "*.otf" \) -exec cp {} /usr/share/fonts/truetype/inter/ \; && \
    rm -rf /tmp/inter /tmp/inter.zip && \
    fc-cache -fv

WORKDIR /app

# Set Puppeteer to use installed Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist

# Create non-root user
RUN groupadd -r renderer && useradd -r -g renderer renderer

# Create directories with proper permissions
RUN mkdir -p /app/tmp /app/output && chown -R renderer:renderer /app

# Create writable fontconfig cache directory for renderer user
# This prevents "No writable cache directories" warnings and speeds up font lookup
RUN mkdir -p /home/renderer/.cache/fontconfig && \
    chown -R renderer:renderer /home/renderer

USER renderer

# Pre-warm fontconfig cache as renderer user (font lookup will be faster)
RUN fc-cache -fv 2>/dev/null || true

# Environment variables for pool configuration
ENV POOL_SIZE=3
ENV MAX_CONCURRENCY=3
ENV PUPPETEER_PROTOCOL_TIMEOUT_MS=600000

# Expose port
EXPOSE 3001

# Health check (increased start-period for browser pool init)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

CMD ["node", "dist/index.js"]

