FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM nginx:1.30-alpine@sha256:0e52bd054126cdc040b1276c0af347aeb02a41b9cfe305d6094767ac30e97949

# direct (por defecto) o caddy; ver docs/deployment/home.md
ENV OPENFINANCE_PROXY_MODE=direct

COPY deploy/docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/docker/nginx/proxy-direct.conf deploy/docker/nginx/proxy-caddy.conf deploy/docker/nginx/security-headers.conf /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
