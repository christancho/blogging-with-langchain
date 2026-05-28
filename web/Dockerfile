FROM node:20-alpine

WORKDIR /app

COPY package*.json .
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["sh", "-c", "npm start -- -p ${PORT:-3000}"]
