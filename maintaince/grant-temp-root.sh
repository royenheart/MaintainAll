#!/bin/bash

# ==========================================
# 脚本名称: grant_temp_sudo.sh
# 功能: 授予指定用户临时 sudo 权限，时长由参数指定
# 用法: sudo ./grant_temp_sudo.sh <用户名> [时长]
#
# 支持的时长格式:
#   紧凑: 30s / 5m / 2h / 1d / 1w
#   单词: 30s, 5min, 2hours, 1day, 1week
#   空格: "30 seconds", "5 minutes", "2 hours", "1 day", "1 week"
# 说明: at 仅有分钟级精度；小于 60 秒时改用后台 sleep 实现
# ==========================================

set -euo pipefail

TARGET_USER="${1:-}"
DURATION_INPUT="${2:-1h}"
SUDOERS_DIR="/etc/sudoers.d"
TEMP_FILE="${SUDOERS_DIR}/temp_sudo_${TARGET_USER}"

# 解析结果:
#   SCHEDULE_MODE=at|sleep
#   AT_TIMESPEC=now + N minutes|hours|days|weeks
#   SLEEP_SECS=N
#   DURATION_DISPLAY=人类可读文案
SCHEDULE_MODE=""
AT_TIMESPEC=""
SLEEP_SECS=0
DURATION_DISPLAY=""

# --- 时长解析 ---

parse_duration() {
    local raw="$1"
    local lower n unit

    # 去掉首尾空白
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"

    if [[ -z "$raw" ]]; then
        echo "❌ 错误: 时长不能为空。" >&2
        exit 1
    fi

    lower=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')

    # 1) 紧凑格式: 30s / 5m / 2h / 1d / 1w
    if [[ "$lower" =~ ^([0-9]+)([smhdw])$ ]]; then
        n="${BASH_REMATCH[1]}"
        unit="${BASH_REMATCH[2]}"
        _set_duration_from_unit "$n" "$unit"
        return 0
    fi

    # 2) 数字 + 可选空白 + 单位词
    #    例: 30s, 5m, 5min, 2h, 2hours, 1d, 1day, "30 minutes"
    if [[ "$lower" =~ ^([0-9]+)[[:space:]]*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks)$ ]]; then
        n="${BASH_REMATCH[1]}"
        unit="${BASH_REMATCH[2]}"
        case "$unit" in
            s|sec|secs|second|seconds) unit=s ;;
            m|min|mins|minute|minutes) unit=m ;;
            h|hr|hrs|hour|hours)       unit=h ;;
            d|day|days)                unit=d ;;
            w|wk|wks|week|weeks)       unit=w ;;
        esac
        _set_duration_from_unit "$n" "$unit"
        return 0
    fi

    echo "❌ 错误: 无法解析时长 '$raw'" >&2
    echo "支持示例: 30s, 5m, 2h, 1d, 1w, \"30 minutes\", \"2 hours\"" >&2
    exit 1
}

_set_duration_from_unit() {
    local n="$1"
    local unit="$2"

    if ! [[ "$n" =~ ^[0-9]+$ ]] || [[ "$n" -le 0 ]]; then
        echo "❌ 错误: 时长数值必须是正整数。" >&2
        exit 1
    fi

    case "$unit" in
        s)
            DURATION_DISPLAY="${n} second(s)"
            if [[ "$n" -lt 60 ]]; then
                # at 不支持秒，短于 1 分钟用 sleep
                SCHEDULE_MODE="sleep"
                SLEEP_SECS="$n"
            else
                # 换算成分钟并向上取整，交给 at
                local mins=$(( (n + 59) / 60 ))
                SCHEDULE_MODE="at"
                AT_TIMESPEC="now + ${mins} minutes"
                if [[ $((n % 60)) -ne 0 ]]; then
                    echo "⚠️  提示: at 仅有分钟精度，${n}s 已向上取整为 ${mins} 分钟。"
                fi
            fi
            ;;
        m)
            DURATION_DISPLAY="${n} minute(s)"
            SCHEDULE_MODE="at"
            AT_TIMESPEC="now + ${n} minutes"
            ;;
        h)
            DURATION_DISPLAY="${n} hour(s)"
            SCHEDULE_MODE="at"
            AT_TIMESPEC="now + ${n} hours"
            ;;
        d)
            DURATION_DISPLAY="${n} day(s)"
            SCHEDULE_MODE="at"
            AT_TIMESPEC="now + ${n} days"
            ;;
        w)
            DURATION_DISPLAY="${n} week(s)"
            SCHEDULE_MODE="at"
            AT_TIMESPEC="now + ${n} weeks"
            ;;
        *)
            echo "❌ 错误: 未知时间单位 '$unit'" >&2
            exit 1
            ;;
    esac
}

schedule_revoke() {
    case "$SCHEDULE_MODE" in
        at)
            # AT_TIMESPEC 形如 "now + 5 minutes"，需要分词传给 at
            # shellcheck disable=SC2086
            if ! echo "rm -f '$TEMP_FILE'" | at $AT_TIMESPEC; then
                echo "❌ 错误: 定时任务设置失败。" >&2
                rm -f "$TEMP_FILE"
                exit 1
            fi
            echo "📅 撤销任务已加入 at 队列，可用 'atq' 查看。"
            ;;
        sleep)
            nohup bash -c "sleep '$SLEEP_SECS'; rm -f '$TEMP_FILE'" >/dev/null 2>&1 &
            disown || true
            echo "⚠️  注意: 少于 60 秒的时长由后台 sleep 实现；机器重启后不会保留该撤销任务。"
            echo "🧾 后台 PID: $!"
            ;;
        *)
            echo "❌ 错误: 内部状态异常，未知调度模式。" >&2
            rm -f "$TEMP_FILE"
            exit 1
            ;;
    esac
}

# --- 检查函数 ---

check_requirements() {
    if [[ $EUID -ne 0 ]]; then
        echo "❌ 错误: 必须以 root 权限运行。" >&2
        exit 1
    fi

    if [[ -z "$TARGET_USER" ]]; then
        echo "❌ 用法: $0 <用户名> [时长]" >&2
        echo "示例: $0 myuser 2h" >&2
        echo "      $0 myuser \"30 minutes\"" >&2
        echo "      $0 myuser 45s" >&2
        exit 1
    fi

    if ! id "$TARGET_USER" &>/dev/null; then
        echo "❌ 错误: 用户 '$TARGET_USER' 不存在。" >&2
        exit 1
    fi

    if ! command -v visudo &>/dev/null; then
        echo "❌ 错误: 未找到 visudo。" >&2
        exit 1
    fi

    # 只有走 at 时才强制要求 atd
    parse_duration "$DURATION_INPUT"

    if [[ "$SCHEDULE_MODE" == "at" ]]; then
        if ! command -v at &>/dev/null; then
            echo "❌ 错误: 未安装 'at'。请执行: apt install at 或 yum install at" >&2
            exit 1
        fi

        if ! systemctl is-active --quiet atd; then
            echo "⚠️  atd 服务未运行，尝试启动..."
            systemctl start atd || { echo "❌ 无法启动 atd 服务"; exit 1; }
        fi
    fi
}

# --- 执行逻辑 ---

main() {
    check_requirements

    echo "------------------------------------------------"
    echo "🔑 正在为 [$TARGET_USER] 配置临时权限..."
    echo "⏳ 有效时长: $DURATION_DISPLAY （输入: $DURATION_INPUT）"

    # 1. 写入 sudoers 规则（默认需要密码）
    # 如需免密，改为: "$TARGET_USER ALL=(ALL) NOPASSWD:ALL"
    echo "$TARGET_USER ALL=(ALL) ALL" > "$TEMP_FILE"
    chmod 0440 "$TEMP_FILE"

    # 2. 校验 sudoers 语法，失败则回滚
    if ! visudo -cf "$TEMP_FILE" >/dev/null; then
        echo "❌ 错误: sudoers 语法校验失败。" >&2
        rm -f "$TEMP_FILE"
        exit 1
    fi

    # 3. 安排到期删除
    schedule_revoke

    echo "✅ 成功！权限将在约 $DURATION_DISPLAY 后自动撤销。"
    echo "📄 临时规则文件: $TEMP_FILE"
    echo "------------------------------------------------"
}

main "$@"
