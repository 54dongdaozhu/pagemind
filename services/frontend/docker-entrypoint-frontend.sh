#!/bin/sh
set -eu

http_template=/etc/nginx/templates/http.conf.template
https_template=/etc/nginx/templates/https.conf.template
nginx_conf=/etc/nginx/conf.d/default.conf

if [ -n "${DOMAIN:-}" ] \
  && [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ] \
  && [ -f "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" ]; then
  envsubst '${DOMAIN}' < "$https_template" > "$nginx_conf"
else
  cp "$http_template" "$nginx_conf"
fi

exec nginx -g "daemon off;"
