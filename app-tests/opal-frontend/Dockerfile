# Use Node image for building the Angular app
FROM node:latest AS build
WORKDIR /app
COPY . .
RUN npm install
RUN npm install -g @angular/cli
RUN ng build --configuration=production
RUN ls -R /app/dist

# Use NGINX to serve the Angular app
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /app/dist/browser /usr/share/nginx/html
EXPOSE 80