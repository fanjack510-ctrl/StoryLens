"""测试用到的仓库路径。

有些测试要读仓库里的真文件——定价表、授权公钥、迁移目录，或者把某个源文件当文本
读进来做结构断言。这些路径原来是相对写的，于是它们的成败取决于**你在哪个目录敲的
pytest**：一批假设仓库根（`config/...`），一批假设 `apps/api`（`app/routers/...`）。

没有任何一个工作目录能让两批同时通过。这件事真正的代价不是几条红线，是**测试总数
不可信**：同一个提交在两个目录下跑出两个失败数，而真出现回归时没人分得清哪几条是
回归、哪几条只是站错了地方。

所以路径从 `__file__` 推，不从 cwd 推。这个文件在 `apps/api/tests/` 下，往上两级是
`apps/api`，往上三级是仓库根。
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["API_ROOT", "REPO_ROOT", "TESTS_DIR", "config_file", "repo_file"]

#: 这个测试树自己所在的目录（`apps/api/tests`）。
#:
#: **仓库里有两个 `tests/`**：这一个，和仓库根下的那一个；两边各有自己的 `fixtures/`。
#: 所以不提供 `fixture_file()` 那种助手——它读起来像「装置目录」，实际只能指向其中一个，
#: 而指错的那次不会报错，只会 FileNotFoundError 在一条和路径无关的测试里。
#: 要哪一个就写清哪一个：`TESTS_DIR / "fixtures"` 或 `repo_file("tests", "fixtures")`。
TESTS_DIR = Path(__file__).resolve().parent

#: `apps/api` —— 后端源码树的根。
API_ROOT = Path(__file__).resolve().parents[1]

#: 仓库根。`config/`、`scripts/`、`docs/` 都挂在这儿。
REPO_ROOT = API_ROOT.parents[1]


def repo_file(*parts: str) -> Path:
    """仓库根下的一个文件。用法：`repo_file("config", "cloud_pricing.json")`。"""
    return REPO_ROOT.joinpath(*parts)


def config_file(name: str) -> Path:
    """`config/` 下的一个文件——这是最常被读到的一类。"""
    return REPO_ROOT / "config" / name
