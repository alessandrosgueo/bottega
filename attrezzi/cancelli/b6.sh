#!/usr/bin/env bash
# Il cancello di B6: i passi di macchina veri in un contenitore Ubuntu pulito (due volte, e il sudoers alla prova),
# poi un sudoers rotto che non si installa. Serve Docker acceso; il contenitore si butta alla fine.
set -euo pipefail
qui="$(cd "$(dirname "$0")" && pwd)"
attrezzi="$(cd "$qui/.." && pwd)"
for prova in b6_macchina.py b6_sudoers_rotto.py; do
  echo "== $prova"
  docker run --rm -v "$attrezzi":/bottega/attrezzi:ro -e PYTHONPATH=/bottega/attrezzi ubuntu:24.04 sh -c \
    "apt-get update -qq >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo python3 >/dev/null 2>&1 && python3 /bottega/attrezzi/cancelli/$prova"
done
