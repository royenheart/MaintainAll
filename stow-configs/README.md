# configs

## stow 链接管理

部分通过 stow 管理配置，如何使用：

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

## dsh 插件

dsh 插件已从 `apps/` 移出，独立放在 `~/projects/dsh-plugins/` 下维护。安装/卸载
统一走 `MaintainAll/deploys/ds-harness/deploy.py`（读 `plugins.yaml` 插件列表，
先 `dsh plugin add <git-url>` 直装，失败再 clone 到本地 `file:` 安装），不再使用
`stow-configs/dsh`、`maintainall.yml`、`cordis:include`，也不再依赖
`install_dsh_plugins` / `uninstall_dsh_plugins` 两个 bash 函数。

单个插件可独立安装/卸载：

```bash
cd ~/projects/dsh-plugins/dsh-plugin-skills-manager
python3 install.py install
python3 install.py uninstall
```

注意：`dsh-plugin-skills-manager` 使用前必须先给 deepseek-harness 应用该插件
`patches/` 目录下的两个补丁（详见插件 README）。
