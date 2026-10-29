FROM node:26-alpine

WORKDIR /app

RUN apk add --no-cache curl

COPY package*.json .
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${PORT:-3000}/api/health || exit 1

CMD ["sh", "-c", "npm start -- -p ${PORT:-3000}"]
