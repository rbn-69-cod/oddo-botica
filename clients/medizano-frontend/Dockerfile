FROM node:20-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /workspace/dist/medical-store-pos/browser /usr/share/nginx/html
COPY ssl/ /etc/nginx/ssl/
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
HEALTHCHECK --interval=10s --timeout=5s --retries=3   CMD wget -q -O - http://127.0.0.1/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
