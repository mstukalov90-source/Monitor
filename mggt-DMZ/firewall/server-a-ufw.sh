#!/bin/bash
# Firewall для сервера А (DMZ) — 172.21.198.222
# RED OS 8.x — firewalld (ufw на этом хосте нет)
#
# Этап: внутреннее тестирование (внешний IP выдадут позже)
# SWEB (77.222.63.161) не затрагивается

set -euo pipefail

ADMIN_NET="172.21.198.0/24"

echo "=== MONITOR DMZ firewall (server A) — firewalld ==="

if ! command -v firewall-cmd &>/dev/null; then
    echo "ERROR: firewalld not found. Install: dnf install firewalld && systemctl enable --now firewalld"
    exit 1
fi

systemctl enable --now firewalld

firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${ADMIN_NET} port port=5432 protocol=tcp accept"
firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=${ADMIN_NET} port port=8000 protocol=tcp accept"

# Когда выдадут внешний IP — раскомментировать:
# firewall-cmd --permanent --add-port=5432/tcp
# firewall-cmd --permanent --add-port=8000/tcp

firewall-cmd --reload

echo "Active rich rules:"
firewall-cmd --list-rich-rules

echo "Done. SWEB not affected."
