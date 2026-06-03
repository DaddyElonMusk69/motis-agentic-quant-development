FROM node:25-slim

WORKDIR /app
COPY package.json ./
COPY apps/web ./apps/web
RUN npm install

WORKDIR /app/apps/web
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
