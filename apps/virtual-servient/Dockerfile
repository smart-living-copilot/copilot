FROM node:22-bookworm AS deps

WORKDIR /app
COPY package*.json ./
RUN npm install

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

FROM deps AS builder

COPY tsconfig.json ./
COPY src ./src
RUN npm run build
RUN npm prune --omit=dev

FROM node:22-slim AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist

ENV REGISTRY_URL=http://wotbot:8123 \
    REDIS_URL=redis://valkey:6379 \
    THING_EVENTS_STREAM=thing_events \
    PORT=3013 \
    WOT_PORT=3014

EXPOSE 3013 3014
CMD ["node", "dist/index.js"]
