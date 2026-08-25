"""构建前检查：spec 里声明要打包的模块，构建用的解释器里真的装了吗。

起因是一次真实事故：`pypdf` 写进了 PyInstaller 的 hiddenimports，但打包用的 .venv 里没装它
——hiddenimports 变不出一个不存在的模块。打包顺利通过，用户导入 PDF 时拿到 500，日志里才是
`ModuleNotFoundError: No module named 'pypdf'`。

开发时用系统 Python 测、产品用 .venv 打包，两个环境不一致就会出这种事。这个检查把它提前到
构建之前——那时它只是一行报错，而不是一份坏掉的安装包。
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "apps" / "api" / "storylens-api.spec"

def main() -> int:
    text = SPEC.read_text(encoding="utf-8")
    block = re.search(r"hiddenimports\s*=\s*\[(.*?)\]", text, re.S)
    if not block:
        print("check_sidecar_imports: 找不到 hiddenimports，跳过")
        return 0
    names = re.findall(r'"([A-Za-z_][\w.]*)"', block.group(1))
    missing = []
    for name in sorted(set(names)):
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 — 装没装上，能不能 import 就是唯一标准
            missing.append(name)
    if missing:
        print("构建用的解释器里缺这些模块（spec 声明要打包，但没装）：")
        for name in missing:
            print("  -", name)
        print("解决：把它们写进 pyproject.toml 的 dependencies，再重新 bootstrap。")
        print("解释器：", sys.executable)
        return 1
    # Keep release-build output ASCII-safe: GitHub's Windows runner may use
    # a cp1252 console even when the repository and sources are UTF-8.
    print(f"check_sidecar_imports: {len(set(names))} modules available")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
