#!/bin/sh
set -eu

required_vars="
LOGIN_PROTECTED_USER
LOGIN_PROTECTED_PASS
LOGIN_CHATCHETO_ATENDEDOR_HOST
LOGIN_CHATCHETO_ATENDEDOR_PORT
LOGIN_CHATCHETO_API_HOST
LOGIN_CHATCHETO_API_PORT
LOGIN_CHATCHETO_GEO_HOST
LOGIN_CHATCHETO_GEO_PORT
LOGIN_CHATCHETO_DASHBOARD_HOST
LOGIN_CHATCHETO_DASHBOARD_PORT
"

for var_name in $required_vars
do
    eval "var_value=\${$var_name:-}"
    if [ -z "$var_value" ]; then
        echo "Falta variable obligatoria: $var_name" >&2
        exit 1
    fi
done

envsubst '${LOGIN_PROTECTED_USER} ${LOGIN_PROTECTED_PASS}' \
    < /etc/nginx/templates/protected-users.map.template \
    > /etc/nginx/conf.d/protected-users.map

envsubst '${LOGIN_CHATCHETO_ATENDEDOR_HOST} ${LOGIN_CHATCHETO_ATENDEDOR_PORT} ${LOGIN_CHATCHETO_API_HOST} ${LOGIN_CHATCHETO_API_PORT} ${LOGIN_CHATCHETO_GEO_HOST} ${LOGIN_CHATCHETO_GEO_PORT} ${LOGIN_CHATCHETO_DASHBOARD_HOST} ${LOGIN_CHATCHETO_DASHBOARD_PORT}' \
    < /etc/nginx/templates/nginx.conf.template \
    > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'
