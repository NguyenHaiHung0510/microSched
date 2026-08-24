FROM node:24-bookworm-slim

WORKDIR /qa/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
RUN npx playwright install --with-deps chromium

COPY frontend/e2e/production-cell/run.mjs /qa/frontend/run.mjs

CMD ["node", "/qa/frontend/run.mjs"]
