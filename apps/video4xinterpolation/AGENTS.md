# Video4x — 方案文档

## 目标

在 `apps/video4xinterpolation` 提供统一的 **Windows 优先** 视频增强工具：

- RIFE 插帧 + Real-ESRGAN 超分（可单独或串联，顺序可选）
- AMD GPU（DirectML）+ NPU（VitisAI）协同；资源实时监控
- CLI（`video4x`）+ Textual 薄壳 TUI

## 包名

- 安装名 / 模块：`video4x`
- 兼容：`rife_amd`、`rife-interpolate` 等旧入口

## 算子

| Op | 说明 |
|----|------|
| `interpolate` | RIFE v4.26，2× 插帧，固定档 ONNX |
| `superresolve` | Real-ESRGAN `x2plus` / `x4plus` / `x4plus_anime`，tile 推理 |

串联时中间结果写临时 mp4，最后一步写用户输出路径。

## Real-ESRGAN GPU+NPU

1. 导出 `realesrgan_full.onnx` + `realesrgan_body.onnx` + `realesrgan_upsample.onnx`，以及 `fixed/256|512`
2. `split-pipeline`：body → **必须** VitisAI（失败则 `RuntimeError`，禁止静默 DML），upsample → DML
3. `cache_key` 由路径派生，避免同名 `realesrgan_body.onnx` 污染缓存
4. 仅缺 body/upsample 文件时回退 full + single-ep

## 依赖

```
numpy, onnxruntime, av, psutil
[export] torch, onnx
[tui] textual
```

## 快捷键（TUI）

| 键 | 功能 |
|----|------|
| Ctrl+R | 开始任务 |
| Ctrl+Q | 退出 |

## 运行环境

- **默认**：conda `ryzen-ai-1.7.1`（VitisAI + DirectML）
- 安装脚本默认把包装进该 conda，**不再强制创建 `.venv`**
- 可选 `.venv`：`setup\windows\install.ps1 -UseVenv`
- 快捷：`. .\setup\windows\env.ps1`

## 帧率

插帧为 **2× 帧数**；输出 FPS = 片源 FPS × 2（自动探测）。30fps→60fps，24fps→48fps。

## RIFE dual-stream（Windows）

`dual-stream`：Stage A（DirectML）与 Stage B（VitisAI 优先）跨相邻 pair 线程重叠；非 Windows 回退顺序 split。单 pair `interpolate` 仍为 A→B 顺序。

## RIFE 共享内存 / IOBinding

`memory_mode=shared`（或 `BackendConfig.use_iobinding=True`）时：

- 预分配 pinned `OrtValue` 槽（双缓冲，兼容 dual-stream 重叠）
- Stage A/B 用 `run_with_iobinding` + `bind_ortvalue_*`，中间张量（flow/mask/feat/…）跨 A→B **同一 `data_ptr`**，不再每帧 `numpy` 往返拷贝
- img0/img1/timestep 写入预分配缓冲一次；`merged` 仅在写出时 `np.copy` 一次取出
- EP 不支持 bind 时明确 fallback，并写入 `fallback_reason` / `iobinding=fallback:…`（不静默假装零拷贝）
- **dual-stream**：无 IOBinding 时跨 pair 线程重叠 A∥B；启用 IOBinding 时改为顺序 A→B（保留 OrtValue 零拷贝）。原因：DirectML Stage A 与 Stage B `run_with_iobinding` 并发不安全（classic A∥classic B 仍可用）

## Real-ESRGAN NPU

导出 `fixed/256x256` 与 `fixed/512x512` 供 VitisAI；首次该 `cache_key` 编译可能很久。`split-pipeline` 下 body 上不了 NPU 会直接失败（不回退 DML）。

## 杂项产物

- `original-info-signature.txt` / `original-model-signature.txt`：运行时 CWD 指纹，已 gitignore
- `models/realesrgan/.gitkeep`：保留目录占位（权重 `*.pth` 本身不入库）
