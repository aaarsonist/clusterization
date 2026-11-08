#!/bin/sh
# Разрешить сетевые подключения к СУБД только по TLS (hostssl) с аутентификацией SCRAM-SHA-256.
set -e
HBA="$PGDATA/pg_hba.conf"
sed -i -E 's/^host([[:space:]]+all[[:space:]]+all[[:space:]]+all[[:space:]]+)/hostssl\1/' "$HBA"
echo "hostnossl all all all reject" >> "$HBA"
