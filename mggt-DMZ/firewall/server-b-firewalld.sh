#!/bin/bash
# Firewall для сервера Б (Backend) — 172.21.198.219
# RED OS 8.0.2, firewalld + Docker Compose
#
# Разрешает 5432/8000 от DMZ (172.21.198.222) и админов (172.21.198.0/24)
# Обязательно: доверить подсеть Docker bridge, иначе API не достучится до db
# SWEB (77.222.63.161) не затрагивается

set -euo pipefail

DMZ_IP="172.21.198.222"
ADMIN_NET="172.21.198.0/24"
DOCKER_SUBNET="172.18.0.0/16"

echo "=== MONITOR Backend firewall (server B) ==="

if ! command -v firewall-cmd &>/dev/null; then
    echo "ERROR: firewalld not found."
    exit 1
fi

systemctl enable --now firewalld

# DMZ + admin access to published ports
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${DMZ_IP} port port=5432 protocol=tcp accept"
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${DMZ_IP} port port=8000 protocol=tcp accept"
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${ADMIN_NET} port port=5432 protocol=tcp accept"
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${ADMIN_NET} port port=8000 protocol=tcp accept"

# Docker Compose internal network (monitor_default)
firewall-cmd --permanent --zone=trusted --add-source="${DOCKER_SUBNET}"

# Bridge interface (имя меняется — подставить актуальное из: docker network inspect monitor_default)
BR_IF=$(ip -br link | awk '/^br-/ {print $1; exit}')
if [[ -n "${BR_IF}" ]]; then
    firewall-cmd --permanent --zone=trusted --add-interface="${BR_IF}" || true
    echo "Trusted bridge interface: ${BR_IF}"
fi

firewall-cmd --reload

echo "Rich rules:"
firewall-cmd --list-rich-rules
echo ""
echo "Trusted sources:"
firewall-cmd --zone=trusted --list-sources

echo ""
echo "Verify: curl -s http://127.0.0.1:8000/health"
echo "SWEB not affected: curl -s http://77.222.63.161:8000/health"
