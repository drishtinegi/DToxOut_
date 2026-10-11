# Multi-stage production Dockerfile for DToxOut frontend

# --- Stage 1: build static bundle ---
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Default is same-origin (nginx proxies /api/ to the backend).
# Override only if the API lives on a different domain.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Stage 2: nginx ---
FROM nginx:1.27-alpine AS runner
RUN rm -rf /usr/share/nginx/html/*
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx image renders *.template files with envsubst at start-up
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Only substitute BACKEND_URL; leave nginx's own $variables alone
ENV NGINX_ENVSUBST_FILTER=BACKEND_URL \
    BACKEND_URL=http://backend:8000

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/healthz || exit 1
