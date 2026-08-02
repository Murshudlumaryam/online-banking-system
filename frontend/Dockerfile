# ---- Development image (used by docker-compose for hot-reload) ----
FROM node:20-alpine

WORKDIR /app

# Install dependencies first (layer caching)
COPY package.json package-lock.json* ./
RUN npm install

# Copy application source
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---------------------------------------------------------------------------
# Production build note (not used by docker-compose, kept here for later):
#
# FROM node:20-alpine AS build
# WORKDIR /app
# COPY package.json package-lock.json* ./
# RUN npm install
# COPY . .
# RUN npm run build
#
# FROM nginx:alpine
# COPY --from=build /app/dist /usr/share/nginx/html
# EXPOSE 80
# CMD ["nginx", "-g", "daemon off;"]
# ---------------------------------------------------------------------------
