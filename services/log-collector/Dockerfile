# SafeOps LogCollector Service
# Node.js webhook ingestion for CI/CD logs

FROM node:18-alpine

# Set working directory
WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm ci --only=production

# Copy source code
COPY src/ ./src/

# Create non-root user for security
RUN addgroup -g 1001 -S safeops && \
    adduser -u 1001 -S safeops -G safeops && \
    chown -R safeops:safeops /app

USER safeops

# Expose the webhook port
EXPOSE 3001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3001/health || exit 1

# Start the service
CMD ["node", "src/index.js"]
