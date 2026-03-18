# Build stage — install build deps, build the Next.js app
FROM node:20-trixie-slim AS builder
ARG SOURCE_DIR=agentex-ui

# Install system dependencies for Sharp (libvips) and native modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips-dev \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set Sharp to use system libvips during build
ENV SHARP_IGNORE_GLOBAL_LIBVIPS=0

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy package files
COPY ${SOURCE_DIR}/package.json ${SOURCE_DIR}/package-lock.json ./

ENV npm_config_cache=/tmp/.npm
RUN npm config set maxsockets 3

# Install all dependencies (including dev for build tooling)
RUN npm config set registry https://registry.npmjs.org/ && \
    npm ci --verbose

# Copy source code
COPY ${SOURCE_DIR} .
COPY LICENSE /app/LICENSE

# Build the application
RUN npm run build

# Remove dev dependencies after build
RUN npm prune --production

# Production stage — clean image without build tools
FROM node:20-trixie-slim AS production
ENTRYPOINT []

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Remove npm and its bundled vulnerable deps (tar, glob, minimatch, cross-spawn)
# npm is not needed at runtime — we run next start directly via node
RUN npm cache clean --force && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

# Copy built application from builder (no build tools, no dev deps)
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/LICENSE ./LICENSE

# Create nonroot user and set ownership
RUN groupadd --system --gid 65532 nonroot && \
    useradd --system --uid 65532 --gid nonroot nonroot && \
    chown -R nonroot:nonroot /app

# Switch to non-root user
USER 65532

EXPOSE 3000

# Start the application directly via node (no npm needed)
CMD ["node", "node_modules/.bin/next", "start"]
