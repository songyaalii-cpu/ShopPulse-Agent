FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -S shoppulse && adduser -S shoppulse -G shoppulse
COPY --from=builder --chown=shoppulse:shoppulse /app/public ./public
COPY --from=builder --chown=shoppulse:shoppulse /app/.next/standalone ./
COPY --from=builder --chown=shoppulse:shoppulse /app/.next/static ./.next/static
USER shoppulse
EXPOSE 3000
CMD ["node", "server.js"]
