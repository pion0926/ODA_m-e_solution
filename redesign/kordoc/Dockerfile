FROM node:22-alpine
WORKDIR /app
COPY redesign/kordoc/package.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund
COPY redesign/kordoc/server.mjs ./server.mjs
EXPOSE 8200
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 CMD wget -qO- http://127.0.0.1:8200/healthz >/dev/null || exit 1
CMD ["node", "server.mjs"]
