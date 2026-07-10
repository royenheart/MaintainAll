# RIFE AMD NPU+GPU 视频插帧

在 AMD Ryzen 8845H 上用 **ONNX Runtime** 做可插拔 RIFE v4.26 插帧。

推理与安装解耦：同一套 `split-pipeline`（Stage A=GPU，Stage B=NPU），按平台选 EP。

| 平台 | Stage A (GPU) | Stage B (NPU) |
|------|---------------|---------------|
| **Windows 原生** | DirectML | VitisAI（Ryzen AI / WinML） |
| **WSL / Linux** | ROCm | VitisAI（WSL 上常不可用 → CPU） |

CLI：`--platform auto|windows|wsl|linux`，可选 `--ep-preference dml,vitisai,cpu`

---

## 路径 A：Windows 原生（推荐打通 NPU+GPU）

管理员 PowerShell：

```powershell
cd D:\Gits\MaintainAll\apps\video4xinterpolation
powershell -ExecutionPolicy Bypass -File setup\windows\install.ps1 -CheckOnly   # 只检查
powershell -ExecutionPolicy Bypass -File setup\windows\install.ps1              # 检查+按需安装
# 可选：-NpuZip C:\Downloads\RAI_*.zip  -RyzenAiInstaller C:\Downloads\ryzen-ai-*.exe
```

已满足版本的驱动 / Ryzen AI / `.venv` 会**跳过**。脚本会打印文档步骤。

Ryzen AI 安装包需从 [AMD 文档](https://ryzenai.docs.amd.com/en/latest/inst.html) 手动下载（普通 AMD 账号 + EULA；非合作伙伴限定）。该软件受美国出口管制 (EAR)：下载/账号校验请使用美国政府允许的地址与合规网络出口 IP；脚本不会代下。详见脚本内「Ryzen AI Software 下载提示」。

**重要（VitisAI）**：Ryzen AI 1.7.1 的 `onnxruntime_vitisai` / `voe` wheel 是 **Python 3.12** 的，装在 conda 环境 `ryzen-ai-1.7.1` 里。若项目 `.venv` 是 3.14 + `onnxruntime-directml`，会报 `VitisAIExecutionProvider missing`。请：

```powershell
powershell -ExecutionPolicy Bypass -File setup\windows\install.ps1 -ForceVenv
# 或直接用 conda：
conda activate ryzen-ai-1.7.1
$env:RYZEN_AI_INSTALLATION_PATH='C:\Program Files\RyzenAI\1.7.1'
pip install -e ".[export,dev]"
powershell -ExecutionPolicy Bypass -File setup\windows\probe_ep.ps1
```

**固定分辨率两档（NPU 推荐）**：VitisAI 不要用动态 H/W。默认档：

| 片源 | pad 后固定 shape | 目录 |
|------|------------------|------|
| 720×1280 | 736×1280 | `models/onnx/fixed/736x1280/` |
| 1080×1920 | 1088×1920 | `models/onnx/fixed/1088x1920/` |

```powershell
.\.venv\Scripts\Activate.ps1
$env:RYZEN_AI_INSTALLATION_PATH='C:\Program Files\RyzenAI\1.7.1'
python scripts\export_onnx.py --fixed-tiers
python scripts\quantize_rife.py
python scripts\interpolate.py in.mp4 out.mp4 --platform windows --backend split-pipeline --memory auto
```

推理按 pad 后尺寸自动选档。Stage B 会子进程探测 VitisAI：量化图失败时自动改用 FP32 瘦图（ConstantOfShape）。`--memory auto|host|pinned|shared` 控制主机缓冲（APU 大共享池时 `auto`→页锁定 shared）。

---

## 路径 B：WSL（GPU 为主；NPU 多为 TODO）

1. **Windows 主机**（为 WSL 透传 `/dev/dxg`，不是原生推理）：

```powershell
powershell -ExecutionPolicy Bypass -File setup\wsl\windows-host.ps1
# 驱动过旧时：
powershell -ExecutionPolicy Bypass -File setup\wsl\windows-host.ps1 -InstallGpu
```

2. **WSL 内**：

```bash
cd setup/wsl
sudo ./install.sh
source ../../.venv/bin/activate
source rocm-wsl.env
```

自检：`bash setup/wsl/verify.sh`

```bash
python scripts/export_onnx.py --full
python scripts/interpolate.py in.mp4 out.mp4 --platform wsl --backend split-pipeline
```

仅 CPU：`sudo ./install.sh --cpu-only`

---

## 使用

| Backend | 说明 |
|---------|------|
| `split-pipeline` | Stage A GPU + Stage B NPU/CPU |
| `cpu-baseline` | 全 CPU |
| `single-ep` | 单 session，按 `ep_preference` |

```python
from rife_amd import RifeInferenceEngine, InferenceConfig

with RifeInferenceEngine(InferenceConfig(mode="split-pipeline", platform="auto")) as engine:
    engine.interpolate_video("in.mp4", "out.mp4")
```

---

## Setup 布局

```
setup/
  windows/install.ps1       # Windows 原生：DML + VitisAI / Ryzen AI
  wsl/windows-host.ps1      # Windows 主机：为 WSL ROCDXG 检查/装 Adrenalin
  wsl/install.sh            # WSL：ROCm/ROCDXG + venv
  wsl/rocm-install.sh
  wsl/verify.sh
```

已知卡点：[docs/known_blockers.md](docs/known_blockers.md)
