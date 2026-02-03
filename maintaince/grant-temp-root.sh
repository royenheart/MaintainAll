#!/bin/bash

# ==========================================
# 脚本名称: grant_temp_sudo.sh
# 功能: 授予指定用户临时 sudo 权限，时长由参数指定
# 用法: sudo ./grant_temp_sudo.sh <用户名> [时长, 如: "30 minutes", "2 hours", "1 day"]
# ==========================================

set -euo pipefail

TARGET_USER="${1:-}"
DURATION="${2:-1 hour}" 
SUDOERS_DIR="/etc/sudoers.d"
TEMP_FILE="${SUDOERS_DIR}/temp_sudo_${TARGET_USER}"

# --- 2. 检查函数 ---

check_requirements() {
    # 检查 root 权限
    if [[ $EUID -ne 0 ]]; then
       echo "❌ 错误: 必须以 root 权限运行。" >&2
       exit 1
    fi

    # 检查用户名是否为空
    if [[ -z "$TARGET_USER" ]]; then
        echo "❌ 用法: $0 <用户名> [时长]" >&2
        echo "示例: $0 myuser \"2 hours\"" >&2
        exit 1
    fi

    # 检查用户是否存在
    if ! id "$TARGET_USER" &>/dev/null; then
        echo "❌ 错误: 用户 '$TARGET_USER' 不存在。" >&2
        exit 1
    fi

    # 检查 at 命令及服务
    if ! command -v at &> /dev/null; then
        echo "❌ 错误: 未安装 'at'。请执行: apt install at 或 yum install at" >&2
        exit 1
    fi

    if ! systemctl is-active --quiet atd; then
        echo "⚠️  atd 服务未运行，尝试启动..."
        systemctl start atd || { echo "❌ 无法启动 atd 服务"; exit 1; }
    fi
}

# --- 3. 执行逻辑 ---

main() {
    check_requirements

    echo "------------------------------------------------"
    echo "🔑 正在为 [$TARGET_USER] 配置临时权限..."
    echo "⏳ 有效时长: $DURATION"

    # 1. 写入 sudoers 规则 (默认需要密码)
    # 如果希望免密，可改为: "$TARGET_USER ALL=(ALL) NOPASSWD:ALL"
    echo "$TARGET_USER ALL=(ALL) ALL" > "$TEMP_FILE"
    
    # 2. 设置权限 (必须是 0440)
    chmod 0440 "$TEMP_FILE"

    # 3. 核心：通过 at 安排删除任务
    # 使用双引号包裹变量以防时长中有空格
    echo "rm -f \"$TEMP_FILE\"" | at now + $DURATION 2>/dev/null | grep "job" || true

    if [[ $? -eq 0 ]]; then
        echo "✅ 成功！权限将在 $DURATION 后自动撤销。"
        echo "📅 撤销任务已加入 at 队列，可用 'atq' 命令查看。"
    else
        echo "❌ 错误: 定时任务设置失败。" >&2
        rm -f "$TEMP_FILE"
        exit 1
    fi
    echo "------------------------------------------------"
}

main
