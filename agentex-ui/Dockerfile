# Build stage — install build deps, build the Next.js app
# Public versioned Chainguard language images require org access; install Node 20 from Wolfi instead.
FROM cgr.dev/chainguard/wolfi-base:latest AS builder
ARG SOURCE_DIR=agentex-ui
ENTRYPOINT []

# Install system dependencies for native modules (node-gyp)
USER root
RUN apk add --no-cache \
    build-base \
    nodejs-20 \
    npm \
    python-3.12

WORKDIR /app

# Disable telemetry during build
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

# Set production environment for the build step
ENV NODE_ENV=production

# Build the application
RUN npm run build

# Remove dev dependencies after build
RUN npm prune --production

# Production stage — clean image without build tools
# Public versioned Chainguard language images require org access; install Node 20 from Wolfi instead.
FROM cgr.dev/chainguard/wolfi-base:latest AS production
ENTRYPOINT []

USER root
RUN apk add --no-cache nodejs-20

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy built application from builder (no build tools, no dev deps)
COPY --from=builder --chown=65532:65532 /app/.next ./.next
COPY --from=builder --chown=65532:65532 /app/node_modules ./node_modules
COPY --from=builder --chown=65532:65532 /app/package.json ./
COPY --from=builder --chown=65532:65532 /app/public ./public
COPY --from=builder --chown=65532:65532 /app/next.config.ts ./
COPY --from=builder --chown=65532:65532 /app/LICENSE ./LICENSE

USER nonroot

EXPOSE 3000

# Start the application directly via node (no npm needed)
CMD ["node", "node_modules/.bin/next", "start"]
