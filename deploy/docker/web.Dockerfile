FROM node:24-alpine AS build

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM nginx:1.27-alpine

# direct (por defecto) o caddy; ver docs/deployment/home.md
ENV OPENFINANCE_PROXY_MODE=direct

COPY deploy/docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/docker/nginx/proxy-direct.conf deploy/docker/nginx/proxy-caddy.conf /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
