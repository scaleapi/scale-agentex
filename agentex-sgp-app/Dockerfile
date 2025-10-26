# Use the official Node.js 20 Debian image
FROM node:20

# Update package lists and install Sharp dependencies
RUN apt-get update && apt-get install -y \
    libvips-dev \
    python3 \
    make \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set Sharp to use system libvips
ENV SHARP_IGNORE_GLOBAL_LIBVIPS=0

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy package files
COPY package.json package-lock.json ./

ENV npm_config_cache=/tmp/.npm
RUN npm config set maxsockets 3

# Install dependencies with better reliability settings
RUN npm config set registry https://registry.npmjs.org/ && \
    npm ci --omit=dev --verbose

# Copy source code (node_modules and .next excluded by .dockerignore)
COPY . .
COPY LICENSE /app/LICENSE

# Build the application (creates fresh .next directory)
RUN npm run build

# Verify build output exists and show final structure
RUN echo "=== Build verification ===" && \
    ls -la .next/ && \
    echo "=== Final container structure ===" && \
    ls -la /app/

# Create non-root user (Debian syntax)
RUN groupadd --system --gid 1001 nodejs && \
    useradd --system --uid 1001 --gid nodejs nextjs

# Change ownership of the entire app directory to nextjs user
RUN chown -R nextjs:nodejs /app

# Switch to non-root user
USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the application
CMD ["npm", "start"] 
