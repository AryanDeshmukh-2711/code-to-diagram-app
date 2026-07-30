FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

# npm install runs at start, not only at build: docker-compose bind-mounts
# ./web over /app, which prevents the named node_modules volume from being
# seeded from the image. Installing here is idempotent and fast once the
# volume is warm, and it keeps hot reload working.
CMD ["sh", "-c", "npm install && npm run dev"]
