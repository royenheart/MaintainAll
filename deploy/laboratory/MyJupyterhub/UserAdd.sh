#!/bin/sh

IFS=$'\n'
for line in $(cat userlist); do
  test -z "$line" && continue
  
  # 提取用户名（第一个字段）
  user=$(echo "$line" | cut -f 1 -d ' ')
  
  # 提取密码（第二个字段到行尾）
  password=$(echo "$line" | cut -f 2- -d ' ')
  
  echo "Adding user $user"
  
  # 创建用户
  useradd -m -s /bin/bash "$user"
  
  # 设置密码
  echo "${user}:${password}" | chpasswd
  
  # 设置家目录权限
  chown -R "$user:$user" "/home/$user"
  chmod -R 700 "/home/$user"
done