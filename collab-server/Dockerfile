FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY server.js ./

EXPOSE 1234
ENV NODE_ENV=production

CMD ["node", "server.js"]
