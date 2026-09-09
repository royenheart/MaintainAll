#!/usr/bin/env bash
# deploy/proxy · rotate.sh — 在代理服务器【本机】全量轮换节点凭据并重建订阅
#
# 在代理服务器上运行（推荐 root 执行；sing-box 用户服务部分会切到 APP_USER）。
#
# 做什么：
#   1. 生成新 hy2 密码与 vless uuid；
#   2. 备份并更新 sing-box config（hy2 users[0].password / vless users[0].uuid）；
#   3. 重启 sing-box 用户服务；
#   4. 用新凭据重建 import-links.txt（地址/端口/WS 路径/标签不变）；
#   5. 重建订阅 base64 静态文件（默认覆盖原文件 → 订阅 URL 不变；KEEP_URL=0 换随机路径）。
#
# 用法：
#   APP_USER=<sing-box用户> [KEEP_URL=0] [ORESTY_CONF_DIR=...] ./rotate.sh [--dry-run]
#
# 例：sudo APP_USER=<sing-box用户> ./rotate.sh --dry-run   # 预览（只读）
#     sudo APP_USER=<sing-box用户> ./rotate.sh             # 正式轮换
#
# 跑完后 daed 侧对同一订阅 URL 点 Update；若手动导入过节点，先删旧节点再导入。

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

APP_USER="${APP_USER:-}"
: "${KEEP_URL:=1}"
: "${ORESTY_CONF_DIR:=/usr/local/openresty/nginx/conf/conf.d}"

say() { echo "[rotate] $*"; }

if [[ -z "${APP_USER}" ]]; then
    echo "usage: APP_USER=<sing-box-user> $0 [--dry-run]" >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
    echo "please run as root (sudo) so openresty/letsencrypt parts can be written" >&2
    exit 2
fi

APP_HOME="$(getent passwd "${APP_USER}" | cut -d: -f6)"
APP_UID="$(id -u "${APP_USER}")"
CFG="${APP_HOME}/.config/sing-box/config.json"
LINKS="${APP_HOME}/.config/sing-box/import-links.txt"
SBOX=""
for c in "${APP_HOME}/.local/bin/sing-box" "/usr/local/bin/sing-box" "/usr/bin/sing-box"; do
    [[ -x "$c" ]] && SBOX="$c" && break
done

say "app=${APP_USER} home=${APP_HOME} dry-run=${DRY_RUN} keep-url=${KEEP_URL}"
[[ -n "$SBOX" ]] || { echo "sing-box binary not found for ${APP_USER}" >&2; exit 9; }
[[ -f "$CFG" ]]   || { echo "config not found: $CFG" >&2; exit 9; }
[[ -f "$LINKS" ]] || { echo "import-links not found: $LINKS" >&2; exit 9; }

SUB_CONF="$(ls ${ORESTY_CONF_DIR}/sub-*.conf 2>/dev/null | head -1 || true)"

# ── 1/4 换凭据 ────────────────────────────────────────────────────────────
PW="$(openssl rand -hex 16)"
UU="$("${SBOX}" generate uuid 2>/dev/null | head -1 | tr -d '\r')"
[ -n "$UU" ] || UU="$(python3 -c 'import uuid; print(uuid.uuid4())')"
say "1/4 new hy2 password + vless uuid generated"

# ── 2/4 更新 config 并重启用户服务 ───────────────────────────────────────
if [[ "${DRY_RUN}" == "1" ]]; then
    say "    (dry-run) 会备份 config/import-links 并写入新凭据、restart sing-box@${APP_USER}"
else
    TS="$(date +%Y%m%d-%H%M%S)"
    cp "$CFG"   "${CFG}.bak-${TS}"
    cp "$LINKS" "${LINKS}.bak-${TS}"
    python3 -c 'import json,sys
p,u,f=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(f))
for i in d.get("inbounds",[]):
    t=i.get("type")
    if t=="hysteria2":
        for x in i.get("users",[]): x["password"]=p
    elif t=="vless":
        for x in i.get("users",[]): x["uuid"]=u
open(f,"w").write(json.dumps(d,indent=2)+"\n")' "$PW" "$UU" "$CFG"
    chown "${APP_USER}" "$CFG"
    "${SBOX}" check -c "$CFG"
    runuser -u "${APP_USER}" -- env "XDG_RUNTIME_DIR=/run/user/${APP_UID}" systemctl --user restart sing-box
    sleep 1
    runuser -u "${APP_USER}" -- env "XDG_RUNTIME_DIR=/run/user/${APP_UID}" systemctl --user is-active sing-box
fi

# ── 3/4 重建 import-links ────────────────────────────────────────────────
if [[ "${DRY_RUN}" == "1" ]]; then
    say "    (dry-run) 会用新凭据重建 ${LINKS}"
else
    mapfile -t OLD < <(grep -vE '^\s*(#|$)' "$LINKS")
    printf '# deploy/proxy import links for daed (rotated %s)\n' "$(date +%F)" > "$LINKS"
    for line in "${OLD[@]}"; do
        case "$line" in
            hysteria2://*) sed "s#^hysteria2://[^@]*@#hysteria2://${PW}@#" <<<"$line" >> "$LINKS" ;;
            vless://*)     sed "s#^vless://[^@]*@#vless://${UU}@#"     <<<"$line" >> "$LINKS" ;;
        esac
    done
    chown "${APP_USER}" "$LINKS"
    echo "=== new import links (real) ==="
    cat "$LINKS"
fi

# ── 4/4 重建订阅 payload（默认覆盖原文件 → URL 不变）───────────────────
if [[ -z "${SUB_CONF}" ]]; then
    say "!! 未找到 ${ORESTY_CONF_DIR}/sub-*.conf，跳过订阅重建（见 sub/README.md）"
elif [[ "${DRY_RUN}" == "1" ]]; then
    say "    (dry-run) 会重建 payload（来源 ${SUB_CONF} 的 alias 指向文件）"
else
    PAY="$(grep -oE 'alias[[:space:]]+[^;]+' "${SUB_CONF}" | head -1 | awk '{print $2}' | tr -d ';')"
    if [[ -z "$PAY" ]]; then
        echo "!! cannot find alias in ${SUB_CONF}" >&2
        exit 9
    fi
    mkdir -p "$(dirname "$PAY")"
    grep -vE '^\s*(#|$)' "$LINKS" | base64 -w0 > "$PAY"
    chmod 644 "$PAY"
    SNI="$(grep -m1 'server_name' "${SUB_CONF}" | awk '{print $2}' | tr -d ';')"
    LOC="$(grep -oE 'location[[:space:]]+=[[:space:]]+[^ ]+' "${SUB_CONF}" | head -1 | awk '{print $3}')"
    echo "payload: $PAY ($(wc -c < "$PAY") bytes)"
    echo "SUB_URL=https://${SNI}${LOC}"
fi

say "完成。daed 侧：同一订阅 URL 点 Update；若手动导入过节点，先删旧节点再导入。"
