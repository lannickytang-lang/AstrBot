# 本地二次开发指南（Custom Dev Guide）

> **本文件属于本地定制内容，不属于上游项目。** 任何参与本仓库开发的 AI 助手或开发者，在开始工作前请先完整阅读本文，并遵守其中的约定。

## 1. 仓库状态与远程配置

本仓库是 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的二次开发（定制）副本。当前配置了两个远程仓库：

| 远程名 | 地址 | 用途 |
|--------|------|------|
| `upstream` | https://github.com/AstrBotDevs/AstrBot.git | 官方上游，**只读**，仅用于 fetch 更新，**永远不要 push** |
| `origin` | git@github.com:lannickytang-lang/AstrBot.git | 本人（lannickytang-lang）的仓库，所有本地提交推送到这里 |

用 `git remote -v` 可随时核对。

## 2. 分支与提交约定

- `master`：与上游保持同步的基准分支，只包含上游代码 + 本指南等少量定制文档
- **定制功能一律在独立分支上开发**（命名如 `feat/xxx`），不要直接改 master
- commit 信息遵循上游的 conventional commits 约定（`feat:` / `fix:` / `docs:` 等）
- 上游 `AGENTS.md` 中的代码规范（ruff 格式化、Google docstring、KISS 原则等）**继续适用**，定制代码也要遵守

## 3. 同步上游更新的标准流程

```bash
git fetch upstream                # 拉取官方最新代码（不合并）
git checkout master
git merge upstream/master         # 合并官方更新
git push origin master            # 推送到自己的仓库

# 把更新同步到定制分支：
git checkout feat/xxx
git rebase master                 # 或 git merge master
```

**冲突处理原则**：优先保留上游逻辑，再在其之上重新套用本地定制；如果不确定如何取舍，停下来询问用户，不要擅自猜测。定制代码尽量走插件（见下节），正常情况下冲突很少。

## 4. 定制原则（重要）

1. **优先使用 AstrBot 插件机制实现定制功能**，不改动 `astrbot/core` 核心代码。插件安装在 `data/plugins/` 目录，开发方法参考官方文档（`docs/zh/`）及插件模板仓库。插件与核心解耦，上游升级几乎不会冲突
2. 确需修改核心代码时：改动尽量集中、少碰无关文件，**每个功能独立 commit**，方便上游合并时定位与排查
3. 不要修改或删除本文件
4. 每次新增定制（功能、核心改动、新配置），**必须在本文件第 5 节登记**

## 5. 定制记录（持续更新）

| 日期 | 分支 / commit | 定制内容 |
|------|---------------|----------|
| 2026-09-26 | master | 初始化二开环境：配置 upstream/origin 双远程、SSH 走 443、新增本指南 |
| 2026-09-26 | master | 新增一键开发启动脚本 `dev.bat` / `dev.ps1`（根目录，双击即同时启动前后端并打开浏览器） |

## 6. 本机环境注意事项

- 操作系统：Windows，shell 为 Git Bash，仓库位于 `D:\tjs\tys\AstrBot`
- 本机代理（Clash 类，fake-ip 模式）会拦截 github.com 的 **22 端口**，SSH 已配置改走 **443 端口**（见 `C:\Users\oyl\.ssh\config`），SSH 认证可用
- 克隆/拉取公开仓库可直接用 HTTPS；push 依赖 SSH（用户名 lannickytang-lang）
- 启动方式见上游 `AGENTS.md`：后端 `uv run main.py`（端口 6185），前端 `cd dashboard && pnpm dev`（端口 3000，`/api` 自动代理到 6185）
- **一键启动**：双击根目录 `dev.bat`（或 PowerShell 执行 `.\dev.bat`），自动弹出前后端两个日志窗口，约 20 秒后打开浏览器访问前端。停止服务：关闭对应窗口即可
- 环境工具链：Python 3.12 / uv / Node 24 / pnpm（已装好；依赖用 `uv sync` 和 `cd dashboard && pnpm install` 安装）
