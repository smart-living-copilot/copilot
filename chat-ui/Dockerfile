FROM node:25-slim AS dev

ARG APP_VERSION=""

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV APP_VERSION=$APP_VERSION
ENV NEXT_PUBLIC_APP_VERSION=$APP_VERSION

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

FROM dev AS build

RUN npm run build

FROM node:25-slim AS runtime

ARG APP_VERSION=""

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./next.config.ts

ENV NEXT_TELEMETRY_DISABLED=1
ENV APP_VERSION=$APP_VERSION
ENV NEXT_PUBLIC_APP_VERSION=$APP_VERSION

EXPOSE 3000

CMD ["npm", "run", "start"]
