#!/usr/bin/env bash
# scripts/assert_test2_host.sh
# Guard: ensure TEST-2 benchmarks run ONLY on WS (192.168.2.24)

set -euo pipefail

EXPECTED_HOST="ws"
EXPECTED_IP="192.168.2.24"

ACTUAL_HOST="$(hostname | tr '[:upper:]' '[:lower:]')"
ACTUAL_IPS="$(hostname -I 2>/dev/null || true)"

if [[ "$ACTUAL_HOST" != "$EXPECTED_HOST" ]]; then
  echo "ERROR: benchmark must run on WS, current host: $ACTUAL_HOST"
  exit 1
fi

case " $ACTUAL_IPS " in
  *" $EXPECTED_IP "*) ;;
  *)
    echo "ERROR: WS IP $EXPECTED_IP not found. Current IPs: $ACTUAL_IPS"
    exit 1
    ;;
esac

echo "Host verification PASSED: $ACTUAL_HOST ($ACTUAL_IPS)"
