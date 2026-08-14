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

## dsh 插件集 (stow-configs/dsh)

MaintainAll 自己的 dsh 插件集统一入口。`stow-configs/dsh` 里**只放
`maintainall.yml`**（插件清单）。

### 原理：嵌套配置加载

dsh 基于 Cordis，内置 `cordis:include`（由 `@deepseek-ai/cordis-plugin-include`
提供）文件加载器，它把一个 YAML 顶层数组解析成 loader entries。所以只需要在你的
cordis 配置里加一条引用，让它去加载 `maintainall.yml`；之后**新增/移除插件只改
`maintainall.yml`，cordis 配置装一次即可，不用再动**。

关键点：`maintainall.yml` 必须放在 **profile 目录**（`$DSH_HOME/profiles/<name>/`）
下，不能放 `$DSH_HOME/` 下。因为 loader 会把 `maintainall.yml` 所在目录当作 baseUrl
去解析 entry 的裸包名——放在 profile 目录里，裸包名才会顺着
`profiles/<name>/node_modules` → `profiles/node_modules` 找到你 `dsh plugin add`
装进去的插件；放在 `$DSH_HOME/` 下则会从 `$DSH_HOME/` 往上找，找不到 profile 里的
node_modules。所以 `cordis:include` 的 `path` 写 `./maintainall.yml`（普通相对路径，
不能用 `!!js`），相对 profile 目录解析到同目录下的 `maintainall.yml`。

### 安装

> 快捷方式：`stow-configs/bash/.bash_my_profile` 里已有 `install_dsh_plugins` /
> `uninstall_dsh_plugins` 两个函数，一键完成下面的 build + link + stow；下面的
> 1-4 步是它们做的事，手动执行时可参考。

1. 构建插件产物（一次；每个插件都要先 build 出 `lib/`）：

```bash
cd apps/dsh-plugin-skills-manager
npm install && npm run build     # tsdown → lib/index.js + lib/client.js
```

2. 把插件装进 profile 的 node_modules（**dsh 正常加载方式：裸包名 + node_modules**；
   插件没发布到 npm，所以用本地路径 `link:` 安装，等价于在 profile 里
   `pnpm add link:<repo>/apps/<name>`）：

```bash
dsh plugin --profile web add link:/home/royenheart/softwares/MaintainAll/apps/dsh-plugin-skills-manager
```

3. stow 软链插件清单到 **profile 目录**（`$DSH_HOME/profiles/web/`）：

```bash
stow dsh -t "${DSH_HOME:-$HOME/.dsh}/profiles/web"
```

4. **手动**修改 cordis 配置（`$DSH_HOME/cordis.patch.yml`，home 级、对每个 profile
   生效），加上下面这条 `cordis:include` 引用：

```yaml
- insert:
    - id: maintainall
      name: cordis:include
      config:
        path: ./maintainall.yml
```

   > cordis 配置是用户自己的文件，这里不 stow、也不自动写；请手动把上面这条加进去。

5. 重启 web profile（`dsh web`）生效。

> 说明：`maintainall.yml` 里每个 entry 的 `name` 写 **npm 包名（裸说明符）**，由
> loader 从 profile 目录（`profiles/web/`）的 node_modules 解析——所以 `maintainall.yml`
> 必须跟 `cordis.yml` 同目录（都放 profile 目录），裸包名才能解析到 `dsh plugin add`
> 装的插件。`cordis:include` 的 `path` 写 `./maintainall.yml`。两者都**不能用 `!!js`**
> （loader 对它们是字面量处理）。换机器时重复第 1、2 步（build + link 安装）即可。

### 后续维护

- **新增/移除插件**：改 `stow-configs/dsh/maintainall.yml`（新增的插件先 build +
  `dsh plugin add link:...`），再重新 `stow dsh`；cordis 配置里那条 `cordis:include`
  引用装一次不用再动。
- **卸载**：删掉 `cordis.patch.yml` 里的 `id: maintainall` 条目、
  `dsh plugin --profile web remove <插件名>`、再 `stow -D dsh -t "$DSH_HOME/profiles/web"`
  取消链接。
