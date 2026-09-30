#!/bin/bash
# DNS / network diagnostic — auto-saves output, hard-timeouts on hang-prone cmds
set -u

OUT="${DNS_CHECK_OUT:-/tmp/dns-check.out}"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

run() {
  # usage: run <seconds> <cmd...>
  local secs="$1"; shift
  if [ -n "$TIMEOUT_BIN" ]; then
    "$TIMEOUT_BIN" --foreground -k 2 "$secs" "$@"
    local rc=$?
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
      echo "[TIMEOUT after ${secs}s] $*"
    fi
    return "$rc"
  else
    echo "[WARN] no timeout(1); running without hard limit: $*"
    "$@"
  fi
}

{
echo "Output file: $OUT"
echo "========== 0. TIME / HOST =========="
date
run 5 hostnamectl 2>/dev/null || hostname
uname -a

echo "========== 1. INTERFACE / IP / ROUTE =========="
ip -br link
ip -4 addr
ip -4 route
ip -6 route 2>/dev/null | head -20

echo "========== 2. RESOLV / RESOLVED =========="
ls -l /etc/resolv.conf
echo "----- /etc/resolv.conf -----"
cat /etc/resolv.conf
echo "----- resolvectl status -----"
run 10 resolvectl status 2>&1
echo "----- systemd-resolved -----"
systemctl is-active systemd-resolved 2>&1 || true
run 10 systemctl status systemd-resolved --no-pager -l 2>&1 | head -40

echo "========== 3. NM / NETPLAN (if any) =========="
if command -v nmcli >/dev/null; then
  run 10 nmcli -f all dev show 2>&1 | egrep -i 'DEVICE|TYPE|STATE|IP4|IP6|DNS|DOMAIN|GATEWAY|ROUTE' || true
fi
ls /etc/netplan 2>/dev/null || true
for f in /etc/netplan/*.yaml; do
  [ -f "$f" ] && echo "----- $f -----" && cat "$f"
done

echo "========== 4. BASIC CONNECTIVITY =========="
run 15 ping -c 3 -W 2 8.8.8.8 2>&1 || true
run 15 ping -c 3 -W 2 1.1.1.1 2>&1 || true
GW=$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')
echo "DEFAULT_GW=${GW:-}"
[ -n "${GW:-}" ] && run 15 ping -c 3 -W 2 "$GW" 2>&1 || true

echo "========== 5. DNS PORT PROBE =========="
echo "--- UDP 53 ---"
run 8 nc -zvu -w 3 8.8.8.8 53 2>&1 || true
run 8 nc -zvu -w 3 1.1.1.1 53 2>&1 || true
echo "--- TCP 53 ---"
run 8 nc -zv -w 3 8.8.8.8 53 2>&1 || true
run 8 nc -zv -w 3 1.1.1.1 53 2>&1 || true
echo "--- TCP 853 (DoT) ---"
run 8 nc -zv -w 3 8.8.8.8 853 2>&1 || true
run 8 nc -zv -w 3 1.1.1.1 853 2>&1 || true

echo "========== 6. DIG MATRIX =========="
for target in 127.0.0.53 8.8.8.8 1.1.1.1; do
  echo "----- dig @$target UDP -----"
  run 8 dig @"$target" example.com +time=2 +tries=1 +stats 2>&1 || true
  echo "----- dig @$target TCP -----"
  run 8 dig @"$target" example.com +tcp +time=2 +tries=1 +stats 2>&1 || true
done
echo "----- dig default (system) -----"
run 8 dig example.com +time=2 +tries=1 +stats 2>&1 || true

echo "----- getent (hard timeout) -----"
run 3 getent hosts example.com 2>&1 || true
run 3 getent ahosts example.com 2>&1 || true
run 3 getent hosts google.com 2>&1 || true

echo "========== 7. HTTP WITHOUT DNS =========="
run 12 curl -sS -I --connect-timeout 5 --max-time 8 https://1.1.1.1 2>&1 | head -20 || true
run 12 curl -sS -I --connect-timeout 5 --max-time 8 https://8.8.8.8 2>&1 | head -20 || true
run 12 curl -sS -I --connect-timeout 5 --max-time 8 \
  --resolve example.com:443:93.184.216.34 https://example.com 2>&1 | head -20 || true

echo "========== 8. FIREWALL / NAT HINTS =========="
if command -v ufw >/dev/null; then
  run 10 sudo -n ufw status verbose 2>&1 || run 15 sudo ufw status verbose 2>&1 || true
fi
run 15 sudo -n iptables -L -n -v 2>&1 | head -80 || run 20 sudo iptables -L -n -v 2>&1 | head -80 || true
run 15 sudo -n iptables -t nat -L -n -v 2>&1 | head -40 || run 20 sudo iptables -t nat -L -n -v 2>&1 | head -40 || true
run 15 sudo -n nft list ruleset 2>&1 | head -120 || run 20 sudo nft list ruleset 2>&1 | head -120 || true

echo "========== 9. LISTENERS ON 53 =========="
run 10 sudo -n ss -ulnp 2>&1 | egrep ':53|:5353' || run 15 sudo ss -ulnp 2>&1 | egrep ':53|:5353' || true
run 10 sudo -n ss -tlnp 2>&1 | egrep ':53|:5353' || run 15 sudo ss -tlnp 2>&1 | egrep ':53|:5353' || true

echo "========== 10. TRACE =========="
if command -v traceroute >/dev/null; then
  run 25 traceroute -n -w 2 -q 1 8.8.8.8 2>&1 | head -20 || true
  echo "----- udp/53 traceroute -----"
  run 25 traceroute -n -U -p 53 -w 2 -q 1 8.8.8.8 2>&1 | head -20 || true
elif command -v tracepath >/dev/null; then
  run 25 tracepath -n 8.8.8.8 2>&1 | head -20 || true
fi

echo "========== 11. CLOUD / DHCP DNS HINTS =========="
for d in 100.100.2.136 100.100.2.138 169.254.169.253 168.63.129.16; do
  echo "----- probe $d:53 udp/tcp -----"
  run 6 nc -zvu -w 2 "$d" 53 2>&1 || true
  run 6 nc -zv  -w 2 "$d" 53 2>&1 || true
  run 5 dig @"$d" example.com +time=1 +tries=1 2>&1 | tail -8 || true
done

echo "========== DONE =========="
echo "Saved to: $OUT"
date
} 2>&1 | tee "$OUT"

echo "Finished. Full log: $OUT"

