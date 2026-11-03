#!/usr/bin/env bash
# TG Hunter: serverga (Ubuntu 22.04/24.04) o'rnatish. Qayta ishga tushirsangiz ham zarar yo'q.
# Old shart: kompyuteringizdagi tg_hunter papkasi serverga /opt/tg_hunter ga nusxalangan bo'lsin (scp bilan), ichida .env va data/.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tg_hunter}"

[ "$(id -u)" -eq 0 ] || { echo "XATO: root sifatida ishga tushiring."; exit 1; }
[ -f "$APP_DIR/docker-compose.yml" ] || { echo "XATO: $APP_DIR/docker-compose.yml topilmadi. Avval papkani scp bilan nusxalang."; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo "XATO: $APP_DIR/.env topilmadi (kalitlar fayli)."; exit 1; }

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# Yangi server birinchi daqiqalarda o'zini sozlaydi (cloud-init, avto-yangilanish) va paket qulfini band qilib turadi.
# Shuning uchun u tugashini kutamiz (eng ko'pi ~5 daqiqa), so'ng davom etamiz.
wait_for_apt() {
  command -v cloud-init >/dev/null 2>&1 && { cloud-init status --wait >/dev/null 2>&1 || true; }
  local i=0
  while [ "$i" -lt 60 ] && command -v fuser >/dev/null 2>&1 \
      && fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock >/dev/null 2>&1; do
    i=$((i + 1))
    sleep 5
  done
}

echo "==> [1/6] Paketlar (yangi server o'zini tayyorlayotgan bo'lsa, bir necha daqiqa kutiladi)"
wait_for_apt
dpkg --configure -a >/dev/null 2>&1 || true
APT=(apt-get -o DPkg::Lock::Timeout=300 -y)
"${APT[@]}" update
"${APT[@]}" install ca-certificates curl ufw unattended-upgrades

echo "==> [2/6] Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null

echo "==> [3/6] Swap 2 GB (OCR/video paytida xotira yetishmasligidan himoya)"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> [4/6] Xavfsizlik: devor (faqat SSH), maxfiy fayllar"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
chmod 600 "$APP_DIR/.env"
mkdir -p "$APP_DIR/data" && chmod 700 "$APP_DIR/data"

echo "==> [5/6] Agent qurilmoqda (birinchi marta 5-10 daqiqa)"
cd "$APP_DIR"
docker compose build

echo "==> [6/6] Tekshiruv (Telegram, bot, kanallar, AI). O'tsagina agent ishga tushiriladi"
if docker compose run --rm -T hunter python -m scripts.check --online; then
  docker compose up -d
elif [ "${FORCE:-0}" = "1" ]; then
  echo "!!! Tekshiruv muvaffaqiyatsiz, lekin FORCE=1 berilgani uchun baribir ishga tushirilmoqda."
  docker compose up -d
else
  echo
  echo "!!! Tekshiruvda muammo bor, agent ISHGA TUSHIRILMADI. Yuqoridagi ❌ qatorlarni tuzating va skriptni qayta ishga tushiring."
  echo "    (Faqat AI kvotasi kabi mayda muammo bo'lsa: FORCE=1 bash $APP_DIR/deploy/server_install.sh)"
  exit 1
fi
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
