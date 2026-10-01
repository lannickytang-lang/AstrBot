# yuansheng AstrBot 一键部署方案

> 状态：方案定稿（2026-10-01），待实施
> 背景：此前部署采用「本地构建镜像 → docker save 2.8G → scp」全量传输，每次后端改动都要传 2.8G，不可持续。本方案改为 **服务器 git 拉取 + 服务器构建**，日常部署传输量降到 KB~MB 级。

---

## 一、架构总览

```
┌── 本地 (Windows) ──────────────┐    ┌── 服务器 (124.222.113.7) ─────────────┐
│                                │    │                                        │
│  deploy/deploy.py              │    │  /root/git/AstrBot.git                 │
│   ① 前置检查(git干净/连通)       │    │   （bare 仓库，纯版本中转站）             │
│   ② git push server dev ───────┼───▶│                                        │
│   ③ 前端 pnpm build → 打包 5MB  │    │  /root/apps/yuansheng-astrbot/         │
│      scp dist.tar.gz ──────────┼───▶│   repo/          ← 工作副本(git pull)   │
│   ④ 上传/更新 server.sh         │    │   data/          ← 数据卷(运行时读)      │
│   ⑤ ssh 调用 server.sh deploy ─┼───▶│   server.sh      ← 服务器端部署脚本      │
│                                │    │        │                               │
│  deploy.py --rollback [时间戳]  │    │   docker build（增量 1~2 分钟）          │
│   └─ ssh 调 server.sh rollback │    │   docker compose up -d                  │
└────────────────────────────────┘    └────────────────────────────────────────┘
```

**双层脚本设计**（应需求 1）：

| 脚本 | 位置 | 用途 |
|------|------|------|
| `deploy/server.sh` | 服务器 `/root/apps/yuansheng-astrbot/server.sh` | 服务器端所有动作。可直接 ssh 登录服务器手动执行（不依赖本地电脑） |
| `deploy/deploy.py` | 本地仓库 | 一条命令完成整个部署：编排 push / 前端构建 / 上传 / 远程调用 server.sh |

### 服务器 git 说明（bare 仓库是什么）

- `git push` 不允许推到"带工作文件的普通仓库"（git 的安全机制），只允许推到 **bare 仓库**（只存版本历史、没有源码工作文件的"纯仓库"）
- 链路：本地 `push` → 服务器 bare 仓库（中转）→ 服务器脚本 `fetch + reset --hard` 同步到工作副本 `repo/`
- **凭证 = 现有 `tudodo.pem`**（本地 `~/.ssh/config` 已配别名 `tudodo-server`），不走 GitHub、无需配置任何新公钥
- 首次 `git push server dev` 是全量历史（一次性，约几十 MB），之后每次增量 KB 级

---

## 二、变更物分类与更新路径

| 变更物 | 更新路径 | 是否重启容器 |
|--------|---------|:---:|
| 后端 Python 代码 | git push → 服务器 pull → 服务器 `docker build` → compose up | ✅ |
| 前端 dist（构建产物，不进 git） | 本地 `pnpm build` → scp（5MB）→ 替换 `data/dist` | ❌ |
| kf 转人工插件 | git push 随代码走 → 服务器从 repo 拷入 `data/plugins/kf_human_transfer/` | ✅ |
| 配置 cmd_config.json / 数据库 | **永不自动动**（服务器 data 卷内，含生产数据） | — |

关键事实：**dashboard 前端不在镜像里**，运行时读 data 卷的 `data/dist`（`assets/version` 必须 = 核心版本 v4.28.1，否则启动时会被官方 dist 下载覆盖）。所以前端更新只传 dist、不动镜像。

### Dockerfile 优化（一次性改动）

现 Dockerfile 顺序是 `COPY . → pip install`，任何代码改动都会使依赖层缓存失效、全量重装依赖（服务器构建要 5-10 分钟）。改为：

```dockerfile
COPY pyproject.toml uv.lock .python-version* ./
RUN uv export ... && uv pip install -r ...   # 依赖层：仅依赖变化时重建
COPY . /AstrBot/                              # 代码层：秒级
```

调整后服务器增量构建约 **1~2 分钟**。

---

## 三、部署流程（deploy.py 全量模式）

```
① 前置检查   本地 git 工作区干净（未提交改动→报错列出）
             ssh tudodo-server 连通
② 推送       git push server dev（把最新代码推到服务器 bare 仓库）
③ 前端       本地 pnpm build → 写 assets/version=v4.28.1 → tar 打包（~5MB）→ scp
④ 服务器脚本  scp server.sh（保持两端一致）→ ssh 执行：
              a. repo: git fetch origin + reset --hard origin/dev（保证与推送一致）
              b. docker build -t yuansheng-astrbot:<时间戳> -t yuansheng-astrbot:latest .
              c. 插件同步: cp -r repo/custom_plugins/kf_human_transfer → data/plugins/
              d. 备份: data_v4.db 快照 + data/dist 打包（都用同一 <时间戳> 命名）
              e. 替换 data/dist（旧的重命名为 dist.old-<时间戳>）
              f. docker compose up -d
              g. 健康检查: 容器 running + 127.0.0.1:6185 探活 + 域名 200
⑤ 摘要输出   版本时间戳、耗时、步骤清单；任一步失败立即中止并打印回滚命令
```

**部分部署**（常用）：
- `python deploy/deploy.py --frontend-only` — 纯前端改动，秒级，不重启容器、不动镜像
- `python deploy/deploy.py --backend-only` — 纯后端/插件改动，跳过前端构建
- `python deploy/deploy.py` — 全量（默认）

---

## 四、版本与回退设计（应需求 2）

### 统一时间戳（stamp）

每次部署生成 `stamp = YYYYMMDD_HHMM`，该次的**镜像 tag、dist 备份、db 快照**全部用它命名：

```
镜像:    yuansheng-astrbot:20261002_2230  +  :latest（latest 指向最新成功部署）
dist:    /root/backups/dist-20261002_2230.tar.gz
数据库:  /root/backups/db-20261002_2230.db
```

### server.sh 子命令

```bash
server.sh list              # 列出所有可回退的时间戳（镜像/dist/db 三列对齐展示）
server.sh rollback <stamp>  # 回退到某一次部署
server.sh status            # 当前版本 + 容器状态 + 健康探活
server.sh backup            # 仅做一次备份（手动）
```

### 回退规则

- `rollback <stamp>` = 该 stamp 的镜像 retag 为 latest → 恢复该 stamp 的 dist → `compose up -d` → 健康检查
- **数据库默认不回退**：回退代码但保留当前数据（否则会丢回退点之后的全部客户消息）。若确需数据一起回退，显式加 `--with-db`：
  - 执行前**自动对当前数据库再做一次即时快照**（安全网，回退错了还能回来）
- **本地一键回退**：`python deploy/deploy.py --rollback`（先 list 供选择）或 `--rollback 20261002_2230` 直接指定
- 备份保留策略：最近 **5** 份，部署成功后自动清理更旧的（镜像另计，见注意事项）

---

## 五、注意事项（实施与使用必读）

1. **磁盘占用**：每个镜像解压后约 2.7G，服务器总盘 40G。镜像保留最近 **3** 个版本 tag（`server.sh rollback` 可用范围），更旧的构建后立即删除；dangling 镜像每次部署顺手 `docker image prune -f`。dist/db 备份很小（dist 5M、db 数 MB），保留 5 份无压力。
2. **重启中断窗口**：`compose up -d` 重建容器约 5~10 秒不可用。期间企微回调若到达，企微官方会**自动重试**（消息不丢，可能延迟）；CSS 客服上下线事件同理。建议在无客户咨询的时段部署。
3. **配置永不覆盖**：脚本绝不触碰 `data/cmd_config.json`、`data/data_v4.db` 内容（备份除外）。所有线上配置改动仍走既有流程（管理台/API/带 bak 的手工编辑）。
4. **`reset --hard` 的边界**：服务器 `repo/` 是纯部署产物，**任何手动改动都会在下次部署被覆盖**——要改代码请改本地仓库再部署。
5. **前端 version 标记**：本地构建后必须写 `assets/version`（=核心版本 v4.28.1），脚本内置；缺它会导致启动时触发官方 dist 下载、覆盖自定义前端（已踩过）。
6. **插件运行份与源码份**：镜像里是源码份（`COPY .` 包含），实际加载的是 `data/plugins/` 运行份——两者靠部署脚本第 c 步保持一致；本地 `custom_plugins/` 改完必须重新部署才生效。
7. **首次实施的一次性动作**：本地 push 全量历史到 bare 仓库（几十 MB）；服务器首次 `docker build`（约 5~8 分钟，之后走缓存 1~2 分钟）。
8. **deploy.py 兼容性**：只依赖 Python 3.10+ 标准库（subprocess 调 ssh/scp/git/pnpm/docker），Windows Git Bash 与 Linux 均可跑；ssh 全程走 `tudodo-server` 别名。
9. **失败即停**：任何一步非零退出立即中止，输出已完成的步骤与"当前线上状态未受影响/受影响"判定 + 对应回滚命令。健康检查失败视同部署失败，自动提示回滚。
10. **部署幂等**：重复执行同一部署无副作用（build 有缓存、dist 覆盖同名、up -d 幂等）。

---

## 六、实施清单（待用户确认后执行）

| # | 动作 | 端 |
|---|------|-----|
| 1 | 本地 `git push server dev`（首次全量） | 本地 |
| 2 | 服务器 clone 工作副本 `repo/` | 服务器 |
| 3 | 改 Dockerfile（依赖层前置）并验证构建 | 双端 |
| 4 | 编写 `deploy/server.sh`（deploy/list/rollback/status/backup） | 服务器 |
| 5 | 编写 `deploy/deploy.py`（含 --frontend-only/--backend-only/--rollback/--with-db） | 本地 |
| 6 | 空跑验证：status/list/backup + 前端-only 真实跑一次（不动镜像） | 双端 |
| 7 | CUSTOM_DEV_GUIDE §5 登记 + 本提交 | 本地 |

## 七、日常使用速查

```bash
python deploy/deploy.py                 # 全量部署
python deploy/deploy.py --frontend-only # 只发前端（最常用，秒级）
python deploy/deploy.py --backend-only  # 只发后端+插件
python deploy/deploy.py --rollback      # 交互式回退（列出历史供选择）
ssh tudodo-server 'bash /root/apps/yuansheng-astrbot/server.sh status'  # 手动查状态
```
