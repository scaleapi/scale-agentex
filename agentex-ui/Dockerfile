# NOTE: -dev variant required at runtime for libvips (Sharp image processing)
FROM 022465994601.dkr.ecr.us-west-2.amazonaws.com/golden/chainguard/node:20-dev
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
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy package files
COPY ${SOURCE_DIR}/package.json ${SOURCE_DIR}/package-lock.json ./

ENV npm_config_cache=/tmp/.npm
RUN npm config set maxsockets 3

# Install dependencies with better reliability settings
RUN npm config set registry https://registry.npmjs.org/ && \
    npm ci --omit=dev --verbose

# Copy source code (node_modules and .next excluded by .dockerignore)
COPY ${SOURCE_DIR} .
COPY LICENSE /app/LICENSE

# Build the application (creates fresh .next directory)
RUN npm run build

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
