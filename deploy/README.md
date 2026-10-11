# Browser deployment

The public browser client wraps `AgentSession`; it does not change game rules.
Each account has its own saved run and completed-run history. Desktop meta
progression is separate. All web games explicitly use the offline Chaos AI.

## Local development

Set `BLACKJACK_REGISTRATION_TOKEN` to a random 16-digit string,
then run `python -m chaos_blackjack.web`. Local HTTP uses a non-Secure cookie.
Production requires `pip install '.[web]'`, Gunicorn behind an HTTPS proxy, and
`BLACKJACK_SECURE_COOKIE=1`. Never commit credentials. Passwords use salted
scrypt hashes; sessions use hashed random tokens and CSRF protection.

## Production on 43.153.209.136

The deployed branch is **`codex/web-deploy`**. The root-owned
`/usr/local/sbin/chaos-blackjack-deploy` fetches that public branch every minute
using `chaos-blackjack-cd.timer`. No GitHub Actions SSH secret is required.
Only push reviewed production code to this branch:

```sh
git push origin codex/web-deploy
```

Every new commit installs its own environment, runs the full offline pytest
suite, integrated GUI smoke test and sound validation, then atomically switches
`/opt/chaos-blackjack/current` and restarts the service. The health check must
report the exact commit; otherwise the prior release is restored. Failed commits
are marked in `/opt/chaos-blackjack/failed/` to avoid continuous retries. Review
the log before removing a particular failed marker to retry. Releases are kept
for manual rollback. Infrastructure files are installed once, so changes under
`deploy/` require an explicit operator installation.

```sh
sudo systemctl status chaos-blackjack chaos-blackjack-cd.timer
sudo journalctl -u chaos-blackjack-cd -n 100 --no-pager
sudo journalctl -u chaos-blackjack -n 100 --no-pager
sudo systemctl start chaos-blackjack-cd.service  # immediate check
```

Runtime data lives in `/var/lib/chaos-blackjack/`: `web.db` stores accounts,
sessions, invitations and per-account runs; `game.db` stores balance data.
Deploys preserve both. Back up SQLite with its `.backup` command or Python's
`sqlite3.Connection.backup()` API rather than copying an active WAL database.

`/etc/chaos-blackjack.env` is root-readable (0600) and initially stores the
invitation and bootstrap admin credentials. The admin account is created only
if absent; restarting never resets its password. Sign in as `admin`, open
**Account**, and change the bootstrap password. Admins can enable/disable users
and generate a new 16-digit invitation; rotation invalidates the old token.
The current invitation's hash is kept in `web.db`; the bootstrap environment
value does not override a rotated invitation. The invitation is reusable until
rotated. Registrations never grant administrator privileges.

Nginx serves HTTPS on 443 and redirects HTTP on 80. Gunicorn binds only to
127.0.0.1:8088. The server firewall and cloud firewall must permit 80 and 443.
The IP certificate is issued by Let's Encrypt with the shortlived profile and
renewed twice daily by `chaos-certbot.timer`; a successful renewal reloads Nginx.

```sh
sudo /opt/chaos-certbot/bin/certbot certonly --non-interactive --agree-tos \
  --register-unsafely-without-email --preferred-profile shortlived \
  --webroot --webroot-path /var/www/chaos-acme --ip-address 43.153.209.136 \
  --deploy-hook 'systemctl reload nginx'
sudo install -m 644 deploy/nginx.conf /etc/nginx/sites-available/chaos-blackjack
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now chaos-blackjack-cd.timer
sudo systemctl start chaos-blackjack-cd.service
```

Initial setup: install Nginx and Python venv support, install Certbot 5.4+ into
`/opt/chaos-certbot`, transfer only `deploy/`, and run `sudo bash deploy/bootstrap.sh`.
The bootstrap script preserves existing databases, credentials and other services.
No private SSH key or local `.env` is transferred.
