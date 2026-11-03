#!/usr/bin/env bash
# TG Hunter: serverga (Ubuntu 22.04/24.04) o'rnatish. Qayta ishga tushirsangiz ham zarar yo'q.
# Old shart: kompyuteringizdagi tg_hunter papkasi serverga /opt/tg_hunter ga nusxalangan bo'lsin (scp bilan), ichida .env va data/.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tg_hunter}"

[ "$(id -u)" -eq 0 ] || { echo "XATO: root sifatida ishga tushiring."; exit 1; }
[ -f "$APP_DIR/docker-compose.yml" ] || { echo "XATO: $APP_DIR/docker-compose.yml topilmadi. Avval papkani scp bilan nusxalang."; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo "XATO: $APP_DIR/.env topilmadi (kalitlar fayli)."; exit 1; }

export DEBIAN_FRONTEND=noninteractive

echo "==> [1/5] Paketlar"
apt-get update -y
apt-get install -y ca-certificates curl ufw unattended-upgrades

echo "==> [2/5] Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null

echo "==> [3/5] Swap 2 GB (OCR/video paytida xotira yetishmasligidan himoya)"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> [4/5] Xavfsizlik: devor (faqat SSH), maxfiy fayllar"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
chmod 600 "$APP_DIR/.env"
mkdir -p "$APP_DIR/data" && chmod 700 "$APP_DIR/data"

echo "==> [5/5] Agent qurilmoqda va ishga tushirilmoqda (birinchi marta 5-10 daqiqa)"
cd "$APP_DIR"
docker compose up -d --build
sleep 8
docker compose ps
echo
docker compose logs --tail 15

cat <<MSG

TAYYOR. Bir necha soniyadan keyin bot sizga "TG Hunter ishga tushdi" deb yozadi.
Foydali buyruqlar (serverda, $APP_DIR papkasida):
  docker compose logs -f --tail 50     loglar
  docker compose ps                    holat
  docker compose down                  to'xtatish
  docker compose up -d --build         yangilash/qayta ishga tushirish
MSG
