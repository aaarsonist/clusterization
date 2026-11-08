# Этап 1: сборка клиентского приложения (строго по lock-файлу)
FROM node:22.22.0-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

# Этап 2: веб-сервер nginx с TLS и обратным проксированием к серверу бизнес-логики
FROM nginx:1.28.1-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
