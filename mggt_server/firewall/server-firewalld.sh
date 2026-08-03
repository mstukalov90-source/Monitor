#!/bin/bash
# MONITOR 172.21.198.219 — firewalld этап 4
# Внешне (шлюз): только M2M :80/:8000
# Внутри 172.21.0.0/16 (корпсеть, в т.ч. .198 и VPN .248): :80/:8000/:5432
# PG и полный WebCRM с интернета — не открывать
set -euo pipefail

CORP="172.21.0.0/16"
GW="192.168.1.217"

echo "=== firewalld BEFORE ==="
firewall-cmd --list-all || true

# Remove legacy DMZ .222
firewall-cmd --permanent --remove-rich-rule='rule family="ipv4" source address="172.21.198.222" port port="5432" protocol="tcp" accept' 2>/dev/null || true
firewall-cmd --permanent --remove-rich-rule='rule family="ipv4" source address="172.21.198.222" port port="8000" protocol="tcp" accept' 2>/dev/null || true

# Idempotent helpers: remove then add
add_rule() {
  local rule="$1"
  firewall-cmd --permanent --remove-rich-rule="$rule" 2>/dev/null || true
  firewall-cmd --permanent --add-rich-rule="$rule"
}

# Localhost PG (WebCRM on host)
add_rule 'rule family="ipv4" source address="127.0.0.1" port port="5432" protocol="tcp" accept'

# Corp LAN
add_rule "rule family=\"ipv4\" source address=\"${CORP}\" port port=\"80\" protocol=\"tcp\" accept"
add_rule "rule family=\"ipv4\" source address=\"${CORP}\" port port=\"8000\" protocol=\"tcp\" accept"
add_rule "rule family=\"ipv4\" source address=\"${CORP}\" port port=\"5432\" protocol=\"tcp\" accept"

# Edge gateway (internal DNS front) — M2M only, no PG
add_rule "rule family=\"ipv4\" source address=\"${GW}\" port port=\"80\" protocol=\"tcp\" accept"
add_rule "rule family=\"ipv4\" source address=\"${GW}\" port port=\"8000\" protocol=\"tcp\" accept"

firewall-cmd --reload

echo "=== firewalld AFTER ==="
firewall-cmd --list-all
firewall-cmd --list-rich-rules
