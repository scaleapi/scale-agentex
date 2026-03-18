# NOTE: -dev variant required at runtime for libvips (Sharp image processing)
FROM cgr.dev/chainguard/node:latest-dev
ARG SOURCE_DIR=public/agentex-ui
ENTRYPOINT []

# Install dependencies as root
USER root
RUN apk add --no-cache \
    libvips-dev \
    python3 \
    make \
    build-base

WORKDIR /app

# Set Sharp to use system libvips
ENV SHARP_IGNORE_GLOBAL_LIBVIPS=0

# Set production environment
ENV NEXT_TELEMETRY_DISABLED=1

# Copy package files
COPY ${SOURCE_DIR}/package.json ${SOURCE_DIR}/package-lock.json ./

ENV npm_config_cache=/tmp/.npm
RUN npm config set maxsockets 3

# Install all dependencies (including dev) needed for build
RUN npm config set registry https://registry.npmjs.org/ && \
    npm ci --verbose

# Copy source code (node_modules and .next excluded by .dockerignore)
COPY ${SOURCE_DIR} .
COPY LICENSE /app/LICENSE

# Build the application (creates fresh .next directory)
ENV NODE_ENV=production
RUN npm run build

# Remove dev dependencies after build
RUN npm prune --omit=dev

# Verify build output exists and show final structure
RUN echo "=== Build verification ===" && \
    ls -la .next/ && \
    echo "=== Final container structure ===" && \
    ls -la /app/

# Use Chainguard's default nonroot user (65532)
RUN chown -R 65532:65532 /app

# Switch to non-root user
USER nonroot

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the application
CMD ["npm", "start"]
