FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

# direct (por defecto) o caddy; ver docs/deployment/home.md
ENV OPENFINANCE_PROXY_MODE=direct

COPY deploy/docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/docker/nginx/proxy-direct.conf deploy/docker/nginx/proxy-caddy.conf deploy/docker/nginx/security-headers.conf /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
