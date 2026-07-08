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
    WOT_RUNTIME_STREAM=wot_runtime_events

EXPOSE 3003
CMD ["node", "dist/index.js"]
