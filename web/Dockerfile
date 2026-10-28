# Demo only: a production build served by `vite preview`, which keeps the /api proxy from
# vite.config.ts (preview.proxy falls back to server.proxy; API_URL is set in compose).
# The dev server was used before; through Docker Desktop's port proxy on Windows its ~100
# unbundled module requests per page load sometimes got connection resets (blank page).
FROM node:22-alpine
WORKDIR /app
# Vite writes a temp file next to vite.config.ts, so /app must belong to the non-root user.
RUN chown node:node /app
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY --chown=node:node . .
RUN npm run build
EXPOSE 5173
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
