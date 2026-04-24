FROM nginx:1.25-alpine

RUN apk add --no-cache gettext openssl \
    && mkdir -p /etc/nginx/tls \
    && openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout /etc/nginx/tls/key.pem \
        -out /etc/nginx/tls/cert.pem \
        -days 365 \
        -subj "/CN=lechuza-server.local" \
    && chmod 600 /etc/nginx/tls/key.pem /etc/nginx/tls/cert.pem

COPY login-service/conf/nginx.conf /etc/nginx/templates/nginx.conf.template
COPY login-service/conf/protected-users.map /etc/nginx/templates/protected-users.map.template
COPY login-service/html /usr/share/nginx/html
COPY login-service/docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
