#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
TASK_PYTHON="$(command -v python3 || true)"
if [[ -z "$TASK_PYTHON" ]]; then
  echo 'Нужен Python 3.11+. Установите его с python.org.'
  read '?Нажмите Enter для закрытия…'
  exit 1
fi
"$TASK_PYTHON" -c 'import sys; assert sys.version_info >= (3,11), "Нужен Python 3.11+"'
mkdir -p .runtime
if [[ ! -x .runtime/collector-venv/bin/python ]]; then
  "$TASK_PYTHON" -m venv .runtime/collector-venv
fi
.runtime/collector-venv/bin/python -m pip install --disable-pip-version-check -r scripts/collector-requirements.txt
# Prefer installed Google Chrome; install the verified Playwright browser only if Chrome is absent.
if [[ ! -d '/Applications/Google Chrome.app' && ! -d "$HOME/Applications/Google Chrome.app" ]]; then
  .runtime/collector-venv/bin/python -m playwright install chromium
fi
printf '\nКакой магазин собрать?\n1 — Maxi\n2 — Moja Pijaca\n3 — Coca-Cola\n'
read 'TASK_STORE?Введите 1, 2 или 3: '
case "$TASK_STORE" in
  1) TASK_SUPPLIER=maxi ;;
  2) TASK_SUPPLIER=moja ;;
  3) TASK_SUPPLIER=coca ;;
  *) echo 'Неизвестный выбор'; exit 1 ;;
esac
.runtime/collector-venv/bin/python scripts/collect_catalog.py --supplier "$TASK_SUPPLIER" --images
printf '\nГотово. Результаты находятся в папке .runtime/collections.\n'
open .runtime/collections
read '?Нажмите Enter для закрытия…'
