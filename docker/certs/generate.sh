#!/bin/sh
# Выпуск сертификатов собственного удостоверяющего центра для TLS между всеми узлами системы.
# Выполняется однократно при первом запуске (служебный контейнер certgen).
set -eu
OUT=/certs
if [ -f "$OUT/ca.crt" ]; then
  echo "Сертификаты уже выпущены"
  exit 0
fi
apk add --no-cache openssl >/dev/null
cd "$OUT"
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes -keyout ca.key -out ca.crt \
  -subj "/C=BY/O=Loyalty Segmentation/CN=Loyalty Segmentation Internal CA" 2>/dev/null

issue() {
  name=$1; san=$2
  openssl req -newkey rsa:2048 -nodes -keyout "$name.key" -out "$name.csr" -subj "/C=BY/O=Loyalty Segmentation/CN=$name" 2>/dev/null
  printf "subjectAltName=%s\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n" "$san" > "$name.ext"
  openssl x509 -req -in "$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -days 825 -sha256 -extfile "$name.ext" -out "$name.crt" 2>/dev/null
  unlink "$name.csr"; unlink "$name.ext"
}
issue frontend "DNS:localhost,IP:127.0.0.1,DNS:frontend"
issue backend_core "DNS:backend_core,DNS:localhost"
issue ai_service "DNS:ai_service,DNS:localhost"
issue postgres "DNS:postgres,DNS:localhost"

chmod 644 ./*.crt
chmod 600 ca.key
chown 70:70 postgres.key && chmod 600 postgres.key
chown 0:10001 backend_core.key ai_service.key && chmod 640 backend_core.key ai_service.key
chmod 600 frontend.key
echo "Сертификаты выпущены"
