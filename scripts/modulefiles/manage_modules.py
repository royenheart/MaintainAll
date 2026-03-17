#!/usr/bin/env python3
"""
manage_modules.py — Environment Modules 配置文件管理工具

功能：
    - 扫描软件安装目录，自动解析软件名/版本，批量生成 modulefile
    - 手动指定软件信息，生成单个 modulefile
    - 列出 / 删除已管理的 modulefile
    - 暴露 PLUGIN_META 接口供 maintain.py TUI 动态加载

独立运行：
    python manage_modules.py                    # 交互式菜单
    python manage_modules.py scan <dir>         # 扫描目录批量生成
    python manage_modules.py add <name> <ver> <path>
    python manage_modules.py list
    python manage_modules.py delete <name> <ver>
    python manage_modules.py --help

模板位置：<repo>/templates/modulefiles/{generic,devel,custom}.tcl
"""

from __future__ import annotations

import os
import re
import sys
import shutil
from pathlib import Path
from typing import Any

# ── 路径定位 ──────────────────────────────────────────────────
# 本脚本位于 scripts/modulefiles/，仓库根为上上层目录
_SCRIPT_DIR = Path(__file__).parent.resolve()
_REPO_ROOT = _SCRIPT_DIR.parent.parent
TEMPLATES_DIR = _REPO_ROOT / "templates" / "modulefiles"

TEMPLATE_FILES = {
    "generic": TEMPLATES_DIR / "generic.tcl",
    "devel":   TEMPLATES_DIR / "devel.tcl",
    "custom":  TEMPLATES_DIR / "custom.tcl",
}

# ── 目录名解析正则 ────────────────────────────────────────────
# 支持分隔符：- 或 _
# 版本号：数字开头，含 . / - / _ 的组合，可选 v 前缀
_VERSION_RE = re.compile(
    r"^(?P<name>[a-zA-Z][a-zA-Z0-9+._-]*?)"   # 软件名（至少一个字母开头）
    r"[-_]"                                    # 分隔符
    r"v?(?P<version>\d[\w.\-]*)$"              # 版本号（可选 v 前缀）
)


# ── 核心数据结构 ──────────────────────────────────────────────

class SoftwareInfo:
    """单个软件的元信息。"""

    def __init__(
        self,
        name: str,
        version: str,
        install_path: Path,
        module_type: str = "generic",
        gen_devel: bool = True,
        extra_entries: str = "",
    ) -> None:
        self.name = name
        self.version = version
        self.install_path = install_path
        self.module_type = module_type
        self.gen_devel = gen_devel
        self.extra_entries = extra_entries  # 仅 custom 模式使用


# ── MODULEPATH 处理 ───────────────────────────────────────────

def get_modulepath() -> list[Path]:
    """读取 $MODULEPATH，返回路径列表（过滤不存在的路径）。"""
    raw = os.environ.get("MODULEPATH", "")
    if not raw:
        return []
    paths = []
    for p in raw.split(":"):
        p = p.strip()
        if p:
            paths.append(Path(p))
    return paths


def choose_output_dir(
    modulepath: list[Path],
    *,
    interactive: bool = True,
    provided: str | None = None,
) -> Path | None:
    """
    选择 modulefile 输出目录。

    优先级：
      1. provided 不为空 → 直接使用（不存在则创建）
      2. modulepath 中第一个位于 $HOME 下的路径
      3. 交互模式：列出全部 modulepath 让用户选择，或手动输入
      4. 非交互模式：返回 None（调用方处理）
    """
    home = Path.home()

    if provided:
        p = Path(provided).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 找第一个在家目录下的路径
    for p in modulepath:
        try:
            p.relative_to(home)
            return p
        except ValueError:
            continue

    # 没有家目录路径
    if not interactive:
        return None

    print("\n未找到位于家目录下的 MODULEPATH 条目。")
    choices: list[Path] = []

    if modulepath:
        print("当前 MODULEPATH 包含以下目录：")
        for i, p in enumerate(modulepath, 1):
            print(f"  [{i}] {p}")
        choices = modulepath

    print(f"  [0] 手动输入新目录")
    raw = input("请选择编号或直接输入路径 [0]: ").strip()

    if raw == "" or raw == "0":
        new_dir = input("请输入目标目录路径: ").strip()
        if not new_dir:
            print("错误：未输入目录路径。")
            return None
        p = Path(new_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
        print("编号超出范围。")
        return None
    except ValueError:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


# ── 目录名解析 ────────────────────────────────────────────────

def parse_dir_name(dirname: str) -> tuple[str, str, str]:
    """
    解析目录名，返回 (name, version, confidence)。
    confidence: "high" | "low"
    """
    m = _VERSION_RE.match(dirname)
    if m:
        name = m.group("name").rstrip("-_")
        version = m.group("version")
        return name, version, "high"

    # 多个 `-` 分隔的情况，尝试最后一段为版本号
    parts = dirname.replace("_", "-").split("-")
    if len(parts) >= 2:
        candidate_ver = parts[-1].lstrip("v")
        if re.match(r"^\d", candidate_ver):
            name = "-".join(parts[:-1])
            return name, candidate_ver, "low"

    # 完全无法解析版本
    return dirname, "", "low"


def _confirm_software_info(
    dirname: str,
    name: str,
    version: str,
    confidence: str,
) -> tuple[str, str] | None:
    """
    交互式确认软件名/版本。
    返回 (name, version) 或 None（用户跳过）。
    """
    if confidence == "high":
        return name, version

    print(f"\n目录 \"{dirname}\"：解析结果 name={name!r}, version={repr(version) or '(未知)'}，置信度较低。")
    print("  [Y] 确认使用此结果")
    print("  [n] 跳过此目录")
    print("  [m] 手动输入")
    choice = input("请选择 [Y/n/m]: ").strip().lower()

    if choice in ("", "y"):
        if not version:
            version = input("  请输入版本号: ").strip()
            if not version:
                print("  跳过（未输入版本号）。")
                return None
        return name, version
    elif choice == "n":
        return None
    elif choice == "m":
        new_name = input(f"  软件名 [{name}]: ").strip() or name
        new_ver  = input(f"  版本号 [{version}]: ").strip() or version
        if not new_ver:
            print("  跳过（未输入版本号）。")
            return None
        return new_name, new_ver
    else:
        return None


# ── 模板加载与渲染 ────────────────────────────────────────────

def load_template(template_type: str) -> str:
    """从 templates/modulefiles/ 加载对应 .tcl 文件内容。"""
    tpl_path = TEMPLATE_FILES.get(template_type)
    if tpl_path is None:
        raise ValueError(f"未知模板类型: {template_type!r}，可选: {list(TEMPLATE_FILES)}")
    if not tpl_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {tpl_path}")
    return tpl_path.read_text(encoding="utf-8")


def _parse_kvlist(raw: str) -> list[tuple[str, str]]:
    """
    解析 kvlist 字符串为 (operation, content) 列表。

    支持格式（每行一条）：
        VAR=/some/path              → prepend-path VAR /some/path
        prepend VAR=/some/path      → prepend-path VAR /some/path
        setenv VAR=value            → setenv VAR value
        append VAR=/some/path       → append-path VAR /some/path
        # 注释行（忽略）
    """
    result = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("setenv "):
            rest = line[7:].strip()
            if "=" in rest:
                var, val = rest.split("=", 1)
                result.append(("setenv", f"{var.strip()} {val.strip()}"))
            continue

        if line.lower().startswith("append "):
            rest = line[7:].strip()
            if "=" in rest:
                var, val = rest.split("=", 1)
                result.append(("append-path", f"{var.strip()} {val.strip()}"))
            continue

        if line.lower().startswith("prepend "):
            rest = line[8:].strip()
        else:
            rest = line

        if "=" in rest:
            var, val = rest.split("=", 1)
            result.append(("prepend-path", f"{var.strip()} {val.strip()}"))

    return result


def _build_custom_entries(kvlist_raw: str) -> str:
    """将 kvlist 原始文本转换为 Tcl modulefile 语句块。"""
    pairs = _parse_kvlist(kvlist_raw)
    lines = []
    for op, content in pairs:
        lines.append(f"{op:<20} {content}")
    return "\n".join(lines)


def render_modulefile(
    template_type: str,
    info: SoftwareInfo,
) -> str:
    """渲染模板，返回最终 Tcl 文件内容。"""
    tpl = load_template(template_type)
    install_path = str(info.install_path)

    tpl = tpl.replace("{{ NAME }}", info.name)
    tpl = tpl.replace("{{ VERSION }}", info.version)
    tpl = tpl.replace("{{ INSTALL_PATH }}", install_path)

    if template_type == "custom":
        custom_block = _build_custom_entries(info.extra_entries)
        tpl = tpl.replace("{{ CUSTOM_ENTRIES }}", custom_block)

    return tpl


# ── 文件写入 / 删除 / 列举 ────────────────────────────────────

def write_modulefile(
    output_dir: Path,
    name: str,
    version: str,
    content: str,
    *,
    overwrite_ok: bool = False,
    interactive: bool = True,
) -> Path | None:
    """
    将 modulefile 内容写入 <output_dir>/<name>/<version>。

    若文件已存在：
        interactive=True  → 询问是否覆盖
        interactive=False → 根据 overwrite_ok 决定
    返回写入路径，或 None（跳过）。
    """
    module_dir = output_dir / name
    module_dir.mkdir(parents=True, exist_ok=True)
    dest = module_dir / version

    if dest.exists():
        if interactive:
            ans = input(f"  文件已存在: {dest}\n  覆盖？[y/N]: ").strip().lower()
            if ans != "y":
                print(f"  跳过 {dest}")
                return None
        elif not overwrite_ok:
            return None

    dest.write_text(content, encoding="utf-8")
    return dest


def list_modulefiles(output_dir: Path) -> list[dict[str, str]]:
    """
    列出 output_dir 下所有已管理的 modulefile。
    返回 [{"name": ..., "version": ..., "path": ...}, ...]
    """
    results = []
    if not output_dir.exists():
        return results
    for name_dir in sorted(output_dir.iterdir()):
        if not name_dir.is_dir():
            continue
        for ver_file in sorted(name_dir.iterdir()):
            if ver_file.is_file():
                results.append({
                    "name":    name_dir.name,
                    "version": ver_file.name,
                    "path":    str(ver_file),
                })
    return results


def delete_modulefile(
    output_dir: Path,
    name: str,
    version: str,
    *,
    del_devel: bool = True,
    interactive: bool = True,
) -> tuple[list[Path], list[Path]]:
    """
    删除 <output_dir>/<name>/<version>（及可选的 <version>-devel）。
    返回 (deleted_paths, not_found_paths)。
    """
    deleted: list[Path] = []
    not_found: list[Path] = []

    targets = [output_dir / name / version]
    if del_devel:
        targets.append(output_dir / name / f"{version}-devel")

    for target in targets:
        if not target.exists():
            not_found.append(target)
            continue
        if interactive:
            ans = input(f"  确认删除 {target}？[y/N]: ").strip().lower()
            if ans != "y":
                print(f"  跳过 {target}")
                continue
        target.unlink()
        deleted.append(target)
        # 若目录为空则删除目录
        parent = target.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    return deleted, not_found


# ── Action Handlers ───────────────────────────────────────────

def action_scan_and_generate(
    fields: dict[str, Any],
    *,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    扫描软件安装根目录，为每个子目录生成 modulefile。

    fields:
        software_dir:  软件安装根目录路径（str）
        module_type:   模板类型（generic/devel/custom），默认 generic
        gen_devel:     是否同时生成 -devel 模块（bool），默认 True
        output_dir:    输出目录（str，留空自动选）
    """
    software_dir = Path(fields.get("software_dir", "")).expanduser().resolve()
    module_type  = fields.get("module_type", "generic")
    gen_devel    = bool(fields.get("gen_devel", True))
    out_provided = fields.get("output_dir", "").strip() or None

    if not software_dir.exists():
        return {"success": False, "message": f"目录不存在: {software_dir}", "data": None}
    if not software_dir.is_dir():
        return {"success": False, "message": f"路径不是目录: {software_dir}", "data": None}

    # 确定输出目录
    modulepath = get_modulepath()
    output_dir = choose_output_dir(modulepath, interactive=interactive, provided=out_provided)
    if output_dir is None:
        return {"success": False, "message": "未能确定输出目录，操作取消。", "data": None}

    # 扫描子目录
    subdirs = sorted(
        p for p in software_dir.iterdir() if p.is_dir()
    )
    if not subdirs:
        return {"success": False, "message": f"目录 {software_dir} 下没有子目录。", "data": None}

    generated: list[str] = []
    skipped:   list[str] = []

    for subdir in subdirs:
        dirname = subdir.name
        name, version, confidence = parse_dir_name(dirname)

        if interactive:
            result = _confirm_software_info(dirname, name, version, confidence)
            if result is None:
                skipped.append(dirname)
                continue
            name, version = result
        else:
            # 非交互模式：低置信度时跳过并报告
            if confidence == "low" and not version:
                skipped.append(f"{dirname}（无法解析版本号）")
                continue
            elif confidence == "low":
                # 低置信度但有候选版本，直接使用
                pass

        info = SoftwareInfo(
            name=name,
            version=version,
            install_path=subdir,
            module_type=module_type,
            gen_devel=gen_devel,
        )

        # 生成主 modulefile
        try:
            content = render_modulefile(module_type, info)
            dest = write_modulefile(
                output_dir, name, version, content,
                overwrite_ok=True, interactive=interactive,
            )
            if dest:
                generated.append(str(dest))
        except Exception as e:
            skipped.append(f"{dirname}（生成失败: {e}）")
            continue

        # 生成 -devel modulefile
        if gen_devel:
            try:
                devel_content = render_modulefile("devel", info)
                devel_dest = write_modulefile(
                    output_dir, name, f"{version}-devel", devel_content,
                    overwrite_ok=True, interactive=interactive,
                )
                if devel_dest:
                    generated.append(str(devel_dest))
            except Exception as e:
                skipped.append(f"{dirname}-devel（生成失败: {e}）")

    msg_parts = [f"已生成 {len(generated)} 个 modulefile，输出目录: {output_dir}"]
    if skipped:
        msg_parts.append(f"跳过 {len(skipped)} 个: {', '.join(skipped)}")
    return {
        "success": True,
        "message": "\n".join(msg_parts),
        "data": {"generated": generated, "skipped": skipped, "output_dir": str(output_dir)},
    }


def action_single_generate(
    fields: dict[str, Any],
    *,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    手动指定软件信息，生成单个 modulefile（及可选 -devel）。

    fields:
        name:          软件名
        version:       版本号
        install_path:  安装路径
        module_type:   模板类型（generic/devel/custom），默认 generic
        gen_devel:     是否同时生成 -devel（bool），默认 True
        extra_entries: 自定义环境变量（kvlist，custom 模式使用）
        output_dir:    输出目录（留空自动选）
    """
    name         = fields.get("name", "").strip()
    version      = fields.get("version", "").strip()
    install_path = Path(fields.get("install_path", "")).expanduser().resolve()
    module_type  = fields.get("module_type", "generic")
    gen_devel    = bool(fields.get("gen_devel", True))
    extra_entries = fields.get("extra_entries", "")
    out_provided = fields.get("output_dir", "").strip() or None

    if not name:
        return {"success": False, "message": "软件名不能为空。", "data": None}
    if not version:
        return {"success": False, "message": "版本号不能为空。", "data": None}
    if not install_path.exists():
        return {"success": False, "message": f"安装路径不存在: {install_path}", "data": None}

    modulepath = get_modulepath()
    output_dir = choose_output_dir(modulepath, interactive=interactive, provided=out_provided)
    if output_dir is None:
        return {"success": False, "message": "未能确定输出目录，操作取消。", "data": None}

    info = SoftwareInfo(
        name=name,
        version=version,
        install_path=install_path,
        module_type=module_type,
        gen_devel=gen_devel,
        extra_entries=extra_entries,
    )

    generated: list[str] = []

    try:
        content = render_modulefile(module_type, info)
        dest = write_modulefile(
            output_dir, name, version, content,
            overwrite_ok=True, interactive=interactive,
        )
        if dest:
            generated.append(str(dest))
    except Exception as e:
        return {"success": False, "message": f"生成失败: {e}", "data": None}

    if gen_devel:
        try:
            devel_content = render_modulefile("devel", info)
            devel_dest = write_modulefile(
                output_dir, name, f"{version}-devel", devel_content,
                overwrite_ok=True, interactive=interactive,
            )
            if devel_dest:
                generated.append(str(devel_dest))
        except Exception as e:
            return {
                "success": True,
                "message": f"主模块已生成，-devel 生成失败: {e}",
                "data": {"generated": generated, "output_dir": str(output_dir)},
            }

    return {
        "success": True,
        "message": f"已生成 {len(generated)} 个文件，输出目录: {output_dir}",
        "data": {"generated": generated, "output_dir": str(output_dir)},
    }


def action_list_modules(
    fields: dict[str, Any],
    *,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    列出指定目录（或 MODULEPATH 首个家目录路径）下所有 modulefile。

    fields:
        output_dir: 目录（留空自动选）
    """
    out_provided = fields.get("output_dir", "").strip() or None

    modulepath = get_modulepath()
    output_dir = choose_output_dir(modulepath, interactive=interactive, provided=out_provided)
    if output_dir is None:
        return {"success": False, "message": "未能确定目录，操作取消。", "data": None}

    modules = list_modulefiles(output_dir)
    if not modules:
        return {
            "success": True,
            "message": f"目录 {output_dir} 下暂无 modulefile。",
            "data": {"modules": [], "output_dir": str(output_dir)},
        }

    lines = [f"目录: {output_dir}，共 {len(modules)} 个 modulefile："]
    for m in modules:
        lines.append(f"  {m['name']}/{m['version']}")
    return {
        "success": True,
        "message": "\n".join(lines),
        "data": {"modules": modules, "output_dir": str(output_dir)},
    }


def action_delete_module(
    fields: dict[str, Any],
    *,
    interactive: bool = False,
) -> dict[str, Any]:
    """
    删除指定 modulefile（及可选 -devel）。

    fields:
        name:       软件名
        version:    版本号
        del_devel:  是否同时删除 -devel（bool），默认 True
        output_dir: 目录（留空自动选）
    """
    name         = fields.get("name", "").strip()
    version      = fields.get("version", "").strip()
    del_devel    = bool(fields.get("del_devel", True))
    out_provided = fields.get("output_dir", "").strip() or None

    if not name:
        return {"success": False, "message": "软件名不能为空。", "data": None}
    if not version:
        return {"success": False, "message": "版本号不能为空。", "data": None}

    modulepath = get_modulepath()
    output_dir = choose_output_dir(modulepath, interactive=interactive, provided=out_provided)
    if output_dir is None:
        return {"success": False, "message": "未能确定目录，操作取消。", "data": None}

    deleted, not_found = delete_modulefile(
        output_dir, name, version,
        del_devel=del_devel,
        interactive=interactive,
    )

    msg_parts = []
    if deleted:
        msg_parts.append(f"已删除 {len(deleted)} 个文件: " + ", ".join(str(p) for p in deleted))
    if not_found:
        msg_parts.append(f"未找到 {len(not_found)} 个文件: " + ", ".join(str(p) for p in not_found))
    if not msg_parts:
        msg_parts.append("操作取消，未删除任何文件。")

    return {
        "success": True,
        "message": "\n".join(msg_parts),
        "data": {
            "deleted":   [str(p) for p in deleted],
            "not_found": [str(p) for p in not_found],
            "output_dir": str(output_dir),
        },
    }


# ── 插件元数据接口（供 maintain.py TUI 动态加载）──────────────

PLUGIN_META: dict[str, Any] = {
    "name": "Environment Modules 管理",
    "description": "生成和管理 Environment Modules (.modulefile) 配置文件",
    "version": "1.0.0",
    "actions": [
        {
            "id": "scan_and_generate",
            "label": "扫描目录批量生成",
            "description": "扫描软件安装根目录，为每个子目录自动生成 modulefile",
            "fields": [
                {
                    "id": "software_dir",
                    "label": "软件安装根目录",
                    "type": "path",
                    "required": True,
                },
                {
                    "id": "module_type",
                    "label": "模板类型",
                    "type": "select",
                    "options": ["generic", "devel", "custom"],
                    "default": "generic",
                    "required": False,
                },
                {
                    "id": "gen_devel",
                    "label": "同时生成 -devel 模块",
                    "type": "bool",
                    "default": True,
                    "required": False,
                },
                {
                    "id": "output_dir",
                    "label": "输出目录（留空自动选）",
                    "type": "path",
                    "required": False,
                },
            ],
            "handler": "action_scan_and_generate",
        },
        {
            "id": "single_generate",
            "label": "手动填写生成单个",
            "description": "手动指定软件名/版本/路径，生成一个 modulefile",
            "fields": [
                {
                    "id": "name",
                    "label": "软件名",
                    "type": "str",
                    "required": True,
                },
                {
                    "id": "version",
                    "label": "版本号",
                    "type": "str",
                    "required": True,
                },
                {
                    "id": "install_path",
                    "label": "安装路径",
                    "type": "path",
                    "required": True,
                },
                {
                    "id": "module_type",
                    "label": "模板类型",
                    "type": "select",
                    "options": ["generic", "devel", "custom"],
                    "default": "generic",
                    "required": False,
                },
                {
                    "id": "gen_devel",
                    "label": "同时生成 -devel 模块",
                    "type": "bool",
                    "default": True,
                    "required": False,
                },
                {
                    "id": "extra_entries",
                    "label": "自定义环境变量（每行 VAR=/path，custom 模式使用）",
                    "type": "kvlist",
                    "required": False,
                },
                {
                    "id": "output_dir",
                    "label": "输出目录（留空自动选）",
                    "type": "path",
                    "required": False,
                },
            ],
            "handler": "action_single_generate",
        },
        {
            "id": "list_modules",
            "label": "列出已管理的 modulefiles",
            "description": "列出 MODULEPATH 首个家目录路径下所有已生成的 modulefile",
            "fields": [
                {
                    "id": "output_dir",
                    "label": "目录（留空自动选）",
                    "type": "path",
                    "required": False,
                },
            ],
            "handler": "action_list_modules",
        },
        {
            "id": "delete_module",
            "label": "删除 modulefile",
            "description": "删除指定软件名+版本的 modulefile（及 -devel）",
            "fields": [
                {
                    "id": "name",
                    "label": "软件名",
                    "type": "str",
                    "required": True,
                },
                {
                    "id": "version",
                    "label": "版本号",
                    "type": "str",
                    "required": True,
                },
                {
                    "id": "del_devel",
                    "label": "同时删除 -devel 模块",
                    "type": "bool",
                    "default": True,
                    "required": False,
                },
                {
                    "id": "output_dir",
                    "label": "目录（留空自动选）",
                    "type": "path",
                    "required": False,
                },
            ],
            "handler": "action_delete_module",
        },
    ],
}


# ── 交互式命令行入口 ──────────────────────────────────────────

def _interactive_scan() -> None:
    """交互式扫描目录批量生成。"""
    software_dir = input("软件安装根目录路径: ").strip()
    if not software_dir:
        print("未输入路径，取消。")
        return

    print("模板类型: [1] generic（默认）  [2] devel  [3] custom")
    t = input("选择 [1]: ").strip()
    type_map = {"1": "generic", "2": "devel", "3": "custom"}
    module_type = type_map.get(t, "generic")

    gen_devel_ans = input("同时生成 -devel 模块？[Y/n]: ").strip().lower()
    gen_devel = gen_devel_ans not in ("n", "no")

    out_dir = input("输出目录（留空自动选）: ").strip() or ""

    result = action_scan_and_generate(
        {
            "software_dir": software_dir,
            "module_type": module_type,
            "gen_devel": gen_devel,
            "output_dir": out_dir,
        },
        interactive=True,
    )
    print("\n" + result["message"])


def _interactive_single() -> None:
    """交互式生成单个 modulefile。"""
    name         = input("软件名: ").strip()
    version      = input("版本号: ").strip()
    install_path = input("安装路径: ").strip()

    print("模板类型: [1] generic（默认）  [2] devel  [3] custom")
    t = input("选择 [1]: ").strip()
    type_map = {"1": "generic", "2": "devel", "3": "custom"}
    module_type = type_map.get(t, "generic")

    gen_devel_ans = input("同时生成 -devel 模块？[Y/n]: ").strip().lower()
    gen_devel = gen_devel_ans not in ("n", "no")

    extra_entries = ""
    if module_type == "custom":
        print("请输入自定义环境变量（每行 VAR=/path 或 setenv VAR=value），空行结束：")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        extra_entries = "\n".join(lines)

    out_dir = input("输出目录（留空自动选）: ").strip() or ""

    result = action_single_generate(
        {
            "name": name,
            "version": version,
            "install_path": install_path,
            "module_type": module_type,
            "gen_devel": gen_devel,
            "extra_entries": extra_entries,
            "output_dir": out_dir,
        },
        interactive=True,
    )
    print("\n" + result["message"])


def _interactive_list() -> None:
    """交互式列出 modulefile。"""
    out_dir = input("目录（留空自动选）: ").strip() or ""
    result = action_list_modules({"output_dir": out_dir}, interactive=True)
    print("\n" + result["message"])


def _interactive_delete() -> None:
    """交互式删除 modulefile。"""
    name    = input("软件名: ").strip()
    version = input("版本号: ").strip()
    del_devel_ans = input("同时删除 -devel 模块？[Y/n]: ").strip().lower()
    del_devel = del_devel_ans not in ("n", "no")
    out_dir = input("目录（留空自动选）: ").strip() or ""
    result = action_delete_module(
        {"name": name, "version": version, "del_devel": del_devel, "output_dir": out_dir},
        interactive=True,
    )
    print("\n" + result["message"])


def interactive_cli() -> None:
    """命令行交互式菜单入口。"""
    print("=" * 50)
    print("  Environment Modules 管理工具")
    print("=" * 50)

    menu = {
        "1": ("扫描目录批量生成",  _interactive_scan),
        "2": ("手动填写生成单个",  _interactive_single),
        "3": ("列出已管理的 modulefiles", _interactive_list),
        "4": ("删除 modulefile",   _interactive_delete),
        "0": ("退出",              None),
    }

    while True:
        print()
        for key, (label, _) in menu.items():
            print(f"  [{key}] {label}")
        choice = input("请选择: ").strip()
        if choice == "0":
            break
        action = menu.get(choice)
        if action is None:
            print("无效选项，请重新输入。")
            continue
        _, fn = action
        try:
            fn()
        except KeyboardInterrupt:
            print("\n（已取消）")


def _print_help() -> None:
    print(__doc__)


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return

    cmd = args[0].lower()

    if cmd == "scan":
        if len(args) < 2:
            print("用法: manage_modules.py scan <软件安装根目录>")
            sys.exit(1)
        result = action_scan_and_generate(
            {"software_dir": args[1], "output_dir": args[2] if len(args) > 2 else ""},
            interactive=True,
        )
        print(result["message"])
        sys.exit(0 if result["success"] else 1)

    elif cmd == "add":
        if len(args) < 4:
            print("用法: manage_modules.py add <name> <version> <install_path> [output_dir]")
            sys.exit(1)
        result = action_single_generate(
            {
                "name":         args[1],
                "version":      args[2],
                "install_path": args[3],
                "output_dir":   args[4] if len(args) > 4 else "",
            },
            interactive=True,
        )
        print(result["message"])
        sys.exit(0 if result["success"] else 1)

    elif cmd == "list":
        result = action_list_modules(
            {"output_dir": args[1] if len(args) > 1 else ""},
            interactive=True,
        )
        print(result["message"])
        sys.exit(0 if result["success"] else 1)

    elif cmd == "delete":
        if len(args) < 3:
            print("用法: manage_modules.py delete <name> <version> [output_dir]")
            sys.exit(1)
        result = action_delete_module(
            {
                "name":       args[1],
                "version":    args[2],
                "output_dir": args[3] if len(args) > 3 else "",
            },
            interactive=True,
        )
        print(result["message"])
        sys.exit(0 if result["success"] else 1)

    else:
        print(f"未知命令: {cmd!r}，使用 --help 查看帮助。")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        try:
            interactive_cli()
        except KeyboardInterrupt:
            print("\n再见。")
    else:
        main()
