# yuansheng-astrbot 一键部署方案

> 版本：v1（2026-10-01 定稿）。目标：本地一条命令完成「推送 → 构建 → 备份 → 更新 → 验证」，支持回退到任意一次部署；彻底告别 2.8G 全量镜像传输。

---

## 1. 架构与角色

```
本地 Windows (D:\tjs\tys\AstrBot)
  └─ python deploy/deploy.py            ← 你/我执行的唯一入口
       │ ① git push origin dev          （GitHub 为唯一代码源头）
       │ ② 本地 pnpm build → dist 5MB   （前端本地构建，快且不吃服务器资源）
       │ ③ scp dist.tar.gz → 服务器
       │ ④ ssh 调用服务器脚本
       ▼
服务器 124.222.113.7 (/root/apps/yuansheng-astrbot)
  └─ ./server.sh <命令>                 ← 服务器端执行体（也可手动登录单独执行）
       ├─ repo/   git fetch --tags && reset --hard deploy/<tag>（只读拉 GitHub，SSH 443）
       ├─ docker build（增量：依赖层已缓存，改代码约 1~2 分钟）
       ├─ 备份三件套（db 快照 + dist + 旧镜像 tag，同一时间戳）
       └─ docker compose up -d + 健康检查
```

**为什么这样分**：
- 代码走 GitHub（唯一源头，服务器只读拉取，无写权限风险）
- 前端本地构建（服务器无 Node 环境，本地 pnpm 已配好）
- 后端服务器构建（Docker 层缓存增量，只传代码不传镜像；首次约 8 分钟，之后 1~2 分钟）
- 双脚本设计：`deploy.py` 编排入口；`server.sh` 独立可执行（紧急时登录服务器直接 `./server.sh rollback <ts>`）

## 2. 服务器目录布局（部署后）

```
/root/apps/yuansheng-astrbot/
├─ docker-compose.yml      # image: yuansheng-astrbot:<时间戳>（由脚本改写）
├─ server.sh               # 服务器端脚本（repo 内 deploy/server.sh 同步而来）
├─ repo/                   # git 工作副本（dev 分支，只读用途）
├─ backups/
│  ├─ db-<ts>.db           # data_v4.db 快照（SQLite backup API，热备安全）
│  └─ dist-<ts>.tar.gz     # 旧前端 dist
└─ data/                   # 数据卷（数据库/插件/知识库/场景模板/客户昵称表）
```

- 镜像 tag：`yuansheng-astrbot:<时间戳>` + `yuansheng-astrbot:latest` 双标签；**旧 tag 不删**（即回退点），仅保留最近 5 个（`docker image prune` 控量）
- 备份保留最近 5 份，更旧的自动清理

### 2.1 版本机制：git tag 固化每次部署

- 本地部署时自动打 **`deploy/<时间戳>`** 标签并 push（如 `deploy/20261001_2330`），部署的精确 commit 从此固化
- 服务器统一 `git fetch --tags && git reset --hard deploy/<tag>`——**强制对齐目标版本，永不冲突**（deploy key 只读可正常 fetch tag）
- `--tag <时间戳>` 参数：把服务器**重部署到任意历史版本**（全新构建旧代码，区别于 rollback 恢复备份，适合对比新旧行为）
- `--list` 的部署历史 = 远端 `deploy/*` 标签列表（含对应 commit 与 note）

### 2.2 运行时数据隔离（为什么不会产生 git 冲突）

- 运行时数据（数据库 data_v4.db、插件运行态 state.json/chat_log.jsonl、知识库、场景模板 analysis_scenarios.json）**全部在 `data/` 目录**，与代码仓库物理分离：服务器上 `repo/`=代码、`data/`=数据卷，互不相交
- 排除规则已验证：`.gitignore:23` 含 `data`（`git ls-files data/` 为空，从未跟踪）；`.dockerignore:22` 含 `data/`；`dashboard/dist/` 同样排除（前端走 scp 通道）
- 服务器 `repo/` 只被脚本 `reset --hard` 管理（不 pull、不手改）→ 双端同改冲突在结构上不存在；红线：**服务器侧禁止手改 repo 内文件**，要改回本地走流程
- 混居注意点：`data/plugins/<name>/` 内源码与运行态同目录，rsync 同步源码时排除 `state.json`、`chat_log.jsonl`、`__pycache__` 等运行态（脚本处理）

## 3. 命令设计

### 本地 `python deploy/deploy.py`

```
python deploy/deploy.py                    # 全量：push+打tag → build → 服务器构建+更新+验收
python deploy/deploy.py --frontend-only    # 纯前端（5MB dist），不重启容器、不碰后端
python deploy/deploy.py --backend-only     # 仅后端（fetch+reset tag + build + up）
python deploy/deploy.py --tag <ts>         # 重部署到历史版本（reset --hard deploy/<ts> 全新构建）
python deploy/deploy.py --list             # 列出历史部署（deploy/* 标签）与备份
python deploy/deploy.py --rollback <ts>    # 回退到指定时间戳（--with-db 连数据库一起回）
python deploy/deploy.py --dry-run          # 只打印将执行的步骤，不动任何东西
```

### 服务器 `./server.sh`（deploy.py 的 ④ 即 ssh 执行它；也可手动用）

```
./server.sh deploy <dist.tar.gz路径>   # pull+build+备份+切换+健康检查（dist 可选传 none 表纯后端）
./server.sh status                     # 容器/版本/磁盘/最近部署
./server.sh list                       # 列出镜像 tag 与备份时间戳
./server.sh rollback <ts> [--with-db]  # 回退
./server.sh frontend <dist.tar.gz>     # 仅换前端
```

## 4. 部署主流程（deploy 全量模式的 7 步）

| 步 | 动作 | 失败处理 |
|----|------|----------|
| ① | 本地检查：工作区干净（有未提交改动则中止）、`git push origin dev` + 打 `deploy/<ts>` 标签并 push | 网络失败重试 1 次，仍失败中止 |
| ② | 本地 `pnpm build` → 校验 `dist/index.html` 存在 → 写 `assets/version`（必须等于 `astrbot.__version__`，缺失会导致启动时官方 dist 下载覆盖我们的前端）→ tar 打包 | 构建失败中止 |
| ③ | scp dist 包到服务器 `/tmp/`（约 5MB，秒级） | 失败中止 |
| ④ | ssh 执行 `server.sh deploy`：`git -C repo fetch --tags + reset --hard deploy/<ts>` → **`docker build`（新时间戳 tag）** → 备份三件套 → 插件目录同步（`repo/custom_plugins/*` → `data/plugins/`，rsync --delete 单插件维度） | build 失败：旧容器未动，直接中止；备份失败中止（宁可不打扰线上） |
| ⑤ | 应用：`data/dist` 原子替换（先解压到 dist.new 再 mv）→ 改写 compose 镜像 tag → `docker compose up -d`（容器重建，停机窗口 ≈ 5 秒） | up 失败：自动执行 rollback 到本时间戳备份 |
| ⑥ | 健康检查（30 秒内重试 3 次）：容器 `Up`、`127.0.0.1:6185` 探活 200、域名 200、登录+`/api/v1/analysis/scenarios` 冒烟、容器日志无 CRITICAL | 检查失败：打印日志摘要 + 提示回滚命令（不自动回滚，留人工判断） |
| ⑦ | 摘要输出：时间戳、commit、前后端变更范围、耗时、回退命令提示 | — |

## 5. 回退机制（核心诉求）

每次部署生成统一时间戳 `ts`（服务器 Asia/Shanghai，格式 `20261001_2330`），三处同戳：

- 镜像 tag `yuansheng-astrbot:<ts>`
- `backups/dist-<ts>.tar.gz`（**该次部署前的**旧 dist）
- `backups/db-<ts>.db`（**该次部署前的** db 快照）

`rollback <ts>` 逻辑：
1. 加载镜像 `<ts>`（若镜像不在但 dist 备份在，仅回退前端也可）
2. 恢复 `dist-<ts>`（该备份对应"部署前状态"，即回到那之前）
3. **数据库默认不动**——代码可以退，客户消息数据绝不丢；旧代码遇到新表（如 kf_customer_profile）不读不报错，安全
4. `--with-db`：先对当前 db 再做一次快照（保底），再恢复 `db-<ts>`；**执行前强制二次确认**（deploy.py 里交互确认，server.sh 手动模式要求输入 YES）
5. `up -d` + 健康检查同部署

`list` 输出示例：
```
ts           commit      note
20261001_2330 06f7590    昵称功能+UI优化
20261001_2208 050c148    数据分析菜单上线
20261001_2140 dce4111    fix: 居中+system过滤
```
（note 取 git log 首行，来自 `repo/.deploynotes`，每次部署追加）

## 6. Dockerfile 分层优化（实施时一并改）

现状：`COPY . /AstrBot` 在依赖安装**之前** → 改一行代码也会重装全部依赖（服务器构建 8-10 分钟）。改为：

```dockerfile
# 1) 先只拷依赖清单，装依赖（不随代码变化，命中缓存）
COPY pyproject.toml uv.lock .python-version ./
RUN python -m pip install uv && uv export ... && uv pip install ...
# 2) 再拷代码（只有这层重建，秒级~分钟级）
COPY . /AstrBot/
```

优化后：纯后端改动 → 服务器构建约 1~2 分钟；依赖变更 → 才走全量层。

## 7. 注意事项与红线（务必读）

**通用红线**
- ⛔ `data/` 卷（数据库/插件/知识库/配置）**永不进镜像、永不进 git**（.gitignore/.dockerignore 已排除；repo 内严禁 `git add data`）
- ⛔ 服务器上其它服务勿动：nginx 只允许 `/etc/nginx/conf.d/` 追加模式（改前备份+`nginx -t`）、宝塔 8888、8601/8090 uvicorn
- ⛔ 企微客服账号管理只在**企微后台**做，勿进 kf.weixin.qq.com（会触发联合版退回 → 机器人失联，历史事故见记忆）
- ⛔ `data/dist/assets/version` 必须 = `astrbot.__version__`（当前 v4.28.1），错配=前端被官方包覆盖
- ⛔ 本地起服测试前必须确认 `platform.wecom.enable=false`（本地实例会抢占生产回调队列，客户消息丢失）——deploy.py 不涉及，人工注意

**流程注意**
- deploy.py 会 push `origin dev`：**部署即发布**，commit 前想清楚；只想备份性推送可先手动 `git push` 再 `--dry-run` 看步骤
- 服务器构建期间旧容器继续运行（build 与 up 分离），客户无感知；只有 `up -d` 重建瞬间约 5 秒窗口，避开咨询高峰更稳
- `repo/` 用 `reset --hard origin/dev`：服务器工作副本**禁止手改文件**（会被下次部署冲掉）；确需服务器侧改动 → 本地改完走流程
- 插件更新 = `repo/custom_plugins/<name>/` → `data/plugins/<name>/` 整目录替换（含 state.json 等运行态的插件注意：kf_human_transfer 的 state.json/chat_log.jsonl 在 data/plugins 运行目录，rsync 时**排除运行态文件**，脚本已处理）
- 回退是"回到那次部署**之前**"的镜像+dist；数据库默认不回退（防丢客户消息）
- 磁盘：镜像每个约 2.7G，保留 5 个 tag + 系统原有，注意 `df -h`（当前 36% 用量，充足）；`server.sh status` 会显示磁盘

**验收口径**
- 每次部署后脚本自动跑健康检查；你人工再过一遍关键功能（客服回复/转人工/数据分析页）
- 建议部署节奏：非高峰（工作日 14:00-17:00 或晚上 22:30 后）

## 8. 当前状态与待办

- [x] 服务器 git 已装（2.43.7）；SSH 走 443 连 GitHub 已配（known_hosts 已加）
- [x] 服务器 Deploy Key 已生成：`/root/.ssh/id_ed25519_github`
- [ ] **【你操作】把公钥加到 GitHub**：打开 https://github.com/lannickytang-lang/AstrBot/settings/keys/new → Title 填 `yuansheng-server-deploy` → 粘贴公钥 → **不勾选 Allow write access**（保持只读）→ Add key
- [ ] 【我操作】验证 GitHub 拉取连通（`ssh -T -p 443 git@ssh.github.com`）→ clone 仓库到 `/root/apps/yuansheng-astrbot/repo`
- [ ] 【我操作】编写 `deploy/server.sh` + `deploy/deploy.py` + Dockerfile 分层优化
- [ ] 【我操作】`--dry-run` 演练 + 你确认后首次真实部署（顺带把当前已验证的昵称功能上线）

## 9. 历史事故与教训（为什么方案长这样）

| 事故/痛点 | 方案对策 |
|-----------|----------|
| 每次部署传输 2.8G 镜像包 | 代码走 git，前端走 5MB 包，后端服务器增量构建 |
| 本地起服抢占企微回调，客户消息丢失 | 本地测试红线：先禁 wecom |
| 前端更新后 dist 版本标记缺失 → 被官方 dist 覆盖 | 构建产物校验 + 自动写 version |
| 分析会话递归污染语料、system_reminder 泄露 | 已修；deploy.py 冒烟检查含 scenarios 接口 |
| 误操作 nginx 影响老站点 | 追加式 + 备份 + nginx -t 红线 |
| 企微联合版被独立版后台退回 | 红线：企微后台管理客服账号 |
| 回退困难（旧镜像无 tag、备份散落） | 统一时间戳三件套 + 一键 rollback |
