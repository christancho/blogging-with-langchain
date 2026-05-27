FROM node:20-alpine

WORKDIR /app

COPY package*.json .
RUN npm ci

COPY . .
ARG NEXT_PUBLIC_API_URL
RUN npm run build

EXPOSE 3000

CMD ["sh", "-c", "npm start -- -p ${PORT:-3000}"]
