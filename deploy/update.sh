#!/usr/bin/env bash
# Installed root-owned outside the source tree. GitHub needs no SSH secrets.
set -Eeuo pipefail
exec 9>/run/lock/chaos-blackjack-deploy.lock
flock -n 9 || exit 0
source /etc/chaos-blackjack-cd.env
base=/opt/chaos-blackjack
repo="$base/repository"
runuser -u chaos-deploy -- git -C "$repo" fetch --quiet origin "$DEPLOY_BRANCH"
sha=$(runuser -u chaos-deploy -- git -C "$repo" rev-parse FETCH_HEAD)
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 1
previous=$(readlink -f "$base/current" || true)
[[ "$previous" != "$base/releases/$sha" ]] || exit 0
# Failed commits are retried only on the next commit or an operator reset.
[[ ! -f "$base/failed/$sha" ]] || exit 1
release="$base/releases/$sha"
mkdir -p "$release" "$base/failed"
chown chaos-deploy:chaos-deploy "$release"
failure() {
    touch "$base/failed/$sha"
    echo "Deployment failed for $sha; the prior release is retained." >&2
}
trap failure ERR
runuser -u chaos-deploy -- bash -e -o pipefail -c 'git -C "$1" archive "$2" | tar -x -C "$3"' _ "$repo" "$sha" "$release"
echo "Testing $sha"
runuser -u chaos-deploy -- python3 -m venv "$release/.venv"
runuser -u chaos-deploy -- "$release/.venv/bin/pip" -q install "$release[web,dev,gui,art]"
runuser -u chaos-deploy -- env CHAOS_USE_LLM=0 CHAOS_DB=:memory: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYTHONUTF8=1 \
    bash -ec 'cd "$1"; .venv/bin/python -m pytest; .venv/bin/python scripts/ci_smoke.py --gui; .venv/bin/python scripts/export_sounds.py --verify' _ "$release"
printf 'BLACKJACK_REVISION=%s\n' "$sha" > "$release/revision.env"
# Runtime user can read a release but cannot alter the deployment source.
chown -R root:root "$release"
chmod -R a+rX "$release"
ln -s "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
if systemctl restart chaos-blackjack && \
    python3 - "$sha" <<'PY'
import json, sys, time, urllib.request
for _ in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/healthz', timeout=2) as r:
            body = json.load(r)
        if body.get('ok') and body.get('revision') == sys.argv[1]:
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)
sys.exit(1)
PY
then
    echo "Deployed $sha"
else
    if [[ -n "$previous" && -d "$previous" ]]; then
        ln -s "$previous" "$base/current.rollback"
        mv -Tf "$base/current.rollback" "$base/current"
        systemctl restart chaos-blackjack
    fi
    failure
    exit 1
fi
