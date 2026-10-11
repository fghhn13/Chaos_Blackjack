#!/usr/bin/env bash
# Run once as root on the explicitly selected Ubuntu server.
set -Eeuo pipefail
cd "$(dirname "$0")"
id chaos-web &>/dev/null || useradd --system --home /var/lib/chaos-blackjack --shell /usr/sbin/nologin chaos-web
id chaos-deploy &>/dev/null || useradd --system --home /opt/chaos-blackjack --shell /usr/sbin/nologin chaos-deploy
install -d -o chaos-web -g chaos-web -m 700 /var/lib/chaos-blackjack
install -d /opt/chaos-blackjack/releases /opt/chaos-blackjack/failed /var/www/chaos-acme
if [[ ! -d /opt/chaos-blackjack/repository ]]; then
    install -d -o chaos-deploy -g chaos-deploy /opt/chaos-blackjack/repository
    runuser -u chaos-deploy -- git clone --quiet https://github.com/fghhn13/Chaos_Blackjack.git /opt/chaos-blackjack/repository
fi
if [[ ! -f /etc/chaos-blackjack.env ]]; then
    python3 - <<'PY'
import os, secrets, string
token = ''.join(secrets.choice(string.digits) for _ in range(16))
password = secrets.token_urlsafe(18)
fd = os.open('/etc/chaos-blackjack.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(f'BLACKJACK_REGISTRATION_TOKEN={token}\nBLACKJACK_ADMIN_USER=admin\nBLACKJACK_ADMIN_PASSWORD={password}\n')
# Only newly generated application credentials; never print infrastructure keys.
print('REGISTRATION_TOKEN=' + token)
print('ADMIN_USER=admin')
print('ADMIN_PASSWORD=' + password)
PY
fi
if [[ ! -f /etc/chaos-blackjack-cd.env ]]; then
    printf 'DEPLOY_BRANCH=codex/web-deploy\n' > /etc/chaos-blackjack-cd.env
    chmod 600 /etc/chaos-blackjack-cd.env
fi
install -m 755 update.sh /usr/local/sbin/chaos-blackjack-deploy
install -m 644 ./*.service ./*.timer /etc/systemd/system/
install -m 644 nginx-http.conf /etc/nginx/sites-available/chaos-blackjack
ln -sf /etc/nginx/sites-available/chaos-blackjack /etc/nginx/sites-enabled/chaos-blackjack
nginx -t
systemctl reload nginx
systemctl daemon-reload
systemctl enable chaos-blackjack.service
systemctl enable --now chaos-certbot.timer
echo 'Bootstrap complete. Request the IP certificate, install nginx.conf, then start chaos-blackjack-cd.timer.'
