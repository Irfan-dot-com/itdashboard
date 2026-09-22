FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG VITE_APP_NAME="IT Dashboard"
ARG VITE_APP_ENV=production
ARG VITE_API_BASE_URL
ARG VITE_ENABLE_MSW=false
ARG VITE_ENABLE_SIMULATION=false
ARG VITE_RELEASE_VERSION=unknown
ENV VITE_APP_NAME=$VITE_APP_NAME
ENV VITE_APP_ENV=$VITE_APP_ENV
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_ENABLE_MSW=$VITE_ENABLE_MSW
ENV VITE_ENABLE_SIMULATION=$VITE_ENABLE_SIMULATION
ENV VITE_RELEASE_VERSION=$VITE_RELEASE_VERSION
RUN npm run build:prod

FROM nginx:1.27-alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
