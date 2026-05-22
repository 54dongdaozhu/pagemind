# ── stage 1: install deps ────────────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ── stage 2: dev server (used by docker-compose.override.yml) ────────────────
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── stage 3: production build ─────────────────────────────────────────────────
FROM deps AS builder
COPY . .
RUN npm run build

# ── stage 4: nginx static server ──────────────────────────────────────────────
FROM nginx:alpine AS runner
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.http.conf.template /etc/nginx/templates/http.conf.template
COPY nginx.https.conf.template /etc/nginx/templates/https.conf.template
COPY docker-entrypoint-frontend.sh /usr/local/bin/docker-entrypoint-frontend.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-frontend.sh
EXPOSE 80
CMD ["docker-entrypoint-frontend.sh"]
