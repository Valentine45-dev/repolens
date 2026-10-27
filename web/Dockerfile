# Demo only: the Vite dev server, proxying /api to the api service (API_URL in compose).
FROM node:22-alpine
WORKDIR /app
# Vite writes a temp file next to vite.config.ts, so /app must belong to the non-root user.
RUN chown node:node /app
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY --chown=node:node . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
