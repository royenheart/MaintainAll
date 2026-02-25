# How to use

1. 进入 configs 配置应用选项
    - jupyterhub 中复制 `jupyterhub_config.example.py` 为 `jupyterhub_config.py` 并根据配置说明更改配置。
2. 配置 jupyterhub 容器选项
    - 复制 `userlist.example` 到 `userlist`，在 `userlist` 中填写管理员账号
3. `docker compose up -d`