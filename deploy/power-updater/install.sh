#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "power updater installation requires root" >&2
  exit 1
fi

scope=${1:-}
case "$scope" in
  ws|prxmx-host|lxc200) ;;
  *)
    echo "usage: $0 ws|prxmx-host|lxc200" >&2
    exit 2
    ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -D -m 0750 "$script_dir/../../scripts/power_auto_updater.py" /usr/local/libexec/power_auto_updater.py
install -D -m 0644 "$script_dir/power-updater.service" /etc/systemd/system/power-updater.service
install -D -m 0644 "$script_dir/power-updater.timer" /etc/systemd/system/power-updater.timer
install -d -m 0750 /etc/power-updater /var/lib/power-updater

umask 077
if [[ "$scope" == "ws" ]]; then
  cat > /etc/power-updater/power-updater.env <<'EOF'
POWER_UPDATER_REPO=weby-homelab/power-framework
POWER_UPDATER_PYTHON_TARGETS=/usr/bin/python3:/root/.config/opencode/venv/bin/python:/root/gemma/projects/P.O.W.E.R/.venv/bin/python:/root/gemma/projects/ai-second-brain-gui/.venv/bin/python:/root/gemma/projects/power-3.6.5-core/.venv/bin/python:/root/gemma/projects/power-gui-3.6.5/.venv/bin/python
POWER_UPDATER_STATE_DIR=/var/lib/power-updater
POWER_UPDATER_GUI=0
POWER_UPDATER_SKILL_TARGETS=/root/.agents/skills/power:/root/.codex/skills/power:/root/.opencode/skills/power:/root/.config/opencode/skills/power:/root/gemma/.agents/skills/power
EOF
elif [[ "$scope" == "prxmx-host" ]]; then
  cat > /etc/power-updater/power-updater.env <<'EOF'
POWER_UPDATER_REPO=weby-homelab/power-framework
POWER_UPDATER_PYTHON_TARGETS=/usr/bin/python3:/root/.config/opencode/venv/bin/python:/root/geminicli/projects/P.O.W.E.R/.venv/bin/python:/root/geminicli/projects/ai-second-brain-gui/venv/bin/python:/root/geminicli/projects/power-framework-work/.venv/bin/python
POWER_UPDATER_STATE_DIR=/var/lib/power-updater
POWER_UPDATER_GUI=0
POWER_UPDATER_SKILL_TARGETS=/root/.agents/skills/power:/root/.codex/skills/power:/root/.opencode/skills/power:/root/.config/opencode/skills/power:/root/geminicli/.agents/skills/power
EOF
else
  cat > /etc/power-updater/power-updater.env <<'EOF'
POWER_UPDATER_REPO=weby-homelab/power-framework
POWER_UPDATER_PYTHON_TARGETS=
POWER_UPDATER_STATE_DIR=/var/lib/power-updater
POWER_UPDATER_GUI=1
POWER_GUI_COMPOSE_DIR=/root/power-gui-build
POWER_GUI_SERVICE=power-gui
POWER_GUI_BASE_IMAGE=webyhomelab/power-gui:0.7.4
POWER_GUI_BIND_ADDRESS=192.168.2.29
POWER_UPDATER_SKILL_TARGETS=
EOF
fi
chmod 0600 /etc/power-updater/power-updater.env
systemctl daemon-reload
systemctl enable --now power-updater.timer
systemctl start power-updater.service
systemctl --no-pager --full status power-updater.timer
