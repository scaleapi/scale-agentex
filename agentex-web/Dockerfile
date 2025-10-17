# Use Node.js LTS (20) as the base image
FROM node:20-alpine AS build

# Set working directory
WORKDIR /app

# Install additional dependencies
RUN apk add --no-cache libc6-compat

# Copy package.json and package-lock.json
COPY package.json package-lock.json ./

# Install dependencies - simplified approach
RUN npm install --no-audit --no-fund

# Copy all files
COPY . .

# Build the application with linting disabled
RUN NEXT_IGNORE_ESLINT_ERRORS=true npx next build --no-lint

# Production image
FROM node:20-alpine AS runner

WORKDIR /app

# Set to production environment
ENV NODE_ENV=production

# Install production dependencies and curl
RUN apk add --no-cache libc6-compat curl

# Copy necessary files from build stage
COPY --from=build /app/package.json ./
COPY --from=build /app/next.config.mjs ./
COPY --from=build /app/.next ./.next
# COPY --from=build /app/public ./public
COPY --from=build /app/node_modules ./node_modules

# Don't run as root
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    chown -R nextjs:nodejs /app
USER nextjs

# Expose the port the app will run on
EXPOSE 3000

# Command to run the app
CMD ["npm", "run", "start"] 