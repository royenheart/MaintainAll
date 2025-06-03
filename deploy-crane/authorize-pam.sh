#!/bin/bash

PAM_FILE="/etc/pam.d/sshd"
BACKUP_FILE="${PAM_FILE}.bak"

# 1. 备份原始文件
sudo cp "$PAM_FILE" "$BACKUP_FILE" || {
    echo "错误：无法创建备份文件"
    exit 1
}

# 2. 执行修改（仅在配置不存在时添加）
if ! grep -q "account.*required.*pam_crane.so" "$PAM_FILE"; then
    sudo sed -i '/^account[[:space:]]\+include[[:space:]]\+password-auth/i account    required     pam_crane.so' "$PAM_FILE"
fi

if ! grep -q "session.*required.*pam_crane.so" "$PAM_FILE"; then
    sudo sed -i '/^session[[:space:]]\+include[[:space:]]\+password-auth/a session    required     pam_crane.so' "$PAM_FILE"
fi

# 3. 验证修改
echo -e "\n=== 修改验证 ==="

# 检查 account 部分
echo "验证 account 配置:"
if grep -A1 -B1 "account.*required.*pam_crane.so" "$PAM_FILE" | grep -q "account.*include.*password-auth"; then
    echo "[成功] pam_crane.so 已正确添加到 account include password-auth 之前"
    grep -A1 -B1 "account.*required.*pam_crane.so" "$PAM_FILE"
else
    echo "[失败] account 部分配置不正确"
    sudo mv "$BACKUP_FILE" "$PAM_FILE"
    exit 1
fi

# 检查 session 部分
echo -e "\n验证 session 配置:"
if grep -A1 -B1 "session.*required.*pam_crane.so" "$PAM_FILE" | grep -q "session.*include.*password-auth"; then
    echo "[成功] pam_crane.so 已正确添加到 session include password-auth 之后"
    grep -A1 -B1 "session.*required.*pam_crane.so" "$PAM_FILE"
else
    echo "[失败] session 部分配置不正确"
    sudo mv "$BACKUP_FILE" "$PAM_FILE"
    exit 1
fi

# 4. 检查 PAM 语法（可选）
cat /etc/pam.d/sshd

echo -e "\n所有修改已验证成功!"
exit 0