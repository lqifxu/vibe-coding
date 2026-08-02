# build
FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_SITE_URL=http://localhost
ENV VITE_SITE_URL=$VITE_SITE_URL

COPY package.json package-lock.json* ./
RUN npm install --registry=https://registry.npmmirror.com

COPY . .
RUN npm run build

# serve + reverse proxy /api
FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
