# stow-configs

如何使用：

1. 首先安装 stow：

```bash
sudo apt install stow
```

2. 将 stow-configs 克隆到本地：

```bash
git clone https://github.com/royenheart/MaintainAll.git
cd MaintainAll
# 安装 bash 配置至生效位置，其余 package 类似
stow bash -t $HOME
```
