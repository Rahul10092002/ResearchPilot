FROM node:20-alpine

WORKDIR /app

# Copy package files first (better layer caching)
COPY package.json package-lock.json* ./

RUN npm install

# Copy rest of the app
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
