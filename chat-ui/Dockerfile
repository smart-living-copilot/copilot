FROM node:25-slim AS dev

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN mkdir -p /app/data

CMD ["sh", "-c", "node scripts/ensure-db.mjs && npm run dev -- --hostname 0.0.0.0"]

FROM dev AS build

RUN npm run build

FROM node:25-slim AS runtime

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./next.config.ts
COPY --from=build /app/scripts ./scripts

ENV NEXT_TELEMETRY_DISABLED=1

RUN mkdir -p /app/data

EXPOSE 3000

CMD ["sh", "-c", "node scripts/ensure-db.mjs && npm run start"]
