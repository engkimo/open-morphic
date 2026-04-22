# =============================================================================
# Morphic-Agent Frontend — Multi-stage Production Dockerfile
# =============================================================================
# Build:  docker build -t morphic-agent-ui .
# Run:    docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8001 morphic-agent-ui
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Install dependencies
# ---------------------------------------------------------------------------
FROM node:22-alpine AS deps

WORKDIR /app

# Copy dependency files for layer caching
COPY package.json package-lock.json ./

# Install production + dev dependencies (dev needed for build step)
RUN npm ci

# ---------------------------------------------------------------------------
# Stage 2: Build the Next.js application
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

# Copy dependencies from previous stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Set build-time env (can be overridden at runtime via NEXT_PUBLIC_*)
ENV NEXT_TELEMETRY_DISABLED=1

# Build the production bundle
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3: Production runtime
# ---------------------------------------------------------------------------
FROM node:22-alpine AS runner

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 nextjs \
    && adduser --system --uid 1001 nextjs

# Copy only what's needed for production
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

USER nextjs

EXPOSE 3000

# Next.js standalone server
CMD ["node", "server.js"]
