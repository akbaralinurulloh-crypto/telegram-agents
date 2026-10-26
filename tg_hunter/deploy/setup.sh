#!/usr/bin/env bash
# TG Hunter: yangi Ubuntu 22.04/24.04 serverni tayyorlash (root sifatida, bir marta ishga tushiriladi, qayta ishga tushirsa ham zarar yo'q).
#   curl -fsSL <shu faylning raw havolasi> | bash        yoki:   bash deploy/setup.sh
set -euo pipefail

REPO_SSH="git@github.com:akbaralinurulloh-crypto/telegram-agents.git"
BRANCH="${BRANCH:-main}"
APP_DIR="/opt/telegram-agents"

[ "$(id -u)" -eq 0 ] || { echo "root sifatida ishga tushiring (sudo -i)"; exit 1; }

echo "==> Paketlar"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git ufw unattended-upgrades

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null

echo "==> Swap (2 GB; OCR/video paytida xotira yetishmasligidan himoya)"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Xavfsizlik devori (faqat SSH)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null

echo "==> GitHub deploy kaliti (faqat o'qish uchun)"
KEY=/root/.ssh/hunter_deploy
mkdir -p /root/.ssh && chmod 700 /root/.ssh
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -C "hunter-server" -f "$KEY" >/dev/null
grep -q "Host github.com" /root/.ssh/config 2>/dev/null || cat >> /root/.ssh/config <<CFG
Host github.com
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
CFG
chmod 600 /root/.ssh/config

if ! git ls-remote "$REPO_SSH" >/dev/null 2>&1; then
  echo
  echo "!!! GitHub hali bu serverga ruxsat bermagan. Quyidagi PUBLIC kalitni nusxalang:"
  echo "------------------------------------------------------------"
  cat "$KEY.pub"
  echo "------------------------------------------------------------"
  echo "GitHub -> repo -> Settings -> Deploy keys -> Add deploy key"
  echo "(Title: hunter-server, kalitni qo'ying, 'Allow write access' BELGILANMASIN), so'ng bu skriptni qayta ishga tushiring."
  exit 2
fi

echo "==> Loyiha"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH" && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_SSH" "$APP_DIR"
fi
mkdir -p "$APP_DIR/tg_hunter/data"
[ -f "$APP_DIR/tg_hunter/.env" ] || cp "$APP_DIR/tg_hunter/.env.example" "$APP_DIR/tg_hunter/.env"
chmod 600 "$APP_DIR/tg_hunter/.env"

cat <<MSG

Server tayyor. Keyingi qadamlar:
  1) nano $APP_DIR/tg_hunter/.env          (kalitlarni yozing; DRY_RUN=true qoldiring)
  2) cd $APP_DIR/tg_hunter
  3) docker compose build
  4) docker compose run --rm hunter python -m scripts.login            (telefon + Telegram kodi)
  5) docker compose run --rm hunter python -m scripts.check --online   (hammasi OK bo'lishi kerak)
  6) docker compose up -d && docker compose logs -f
MSG
