# Deep Interview Spec: AstrBot 微信客服机器人 — 云服务器部署与企微全流程打通

## Metadata
- Interview ID: di-20261001-yuansheng-wecom-kf
- Rounds: 4（Round 0 拓扑 + 3 轮问答）
- Final Ambiguity Score: 13%
- Type: brownfield
- Generated: 2026-10-01
- Threshold: 0.2
- Threshold Source: default（用户与项目 settings 均未配置 `omc.deepInterview.ambiguityThreshold`）
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.90 | 0.35 | 0.315 |
| Constraint Clarity | 0.85 | 0.25 | 0.2125 |
| Success Criteria Clarity | 0.85 | 0.25 | 0.2125 |
| Context Clarity | 0.85 | 0.15 | 0.1275 |
| **Total Clarity** | | | **0.8675** |
| **Ambiguity** | | | **13%** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 打包与服务器部署 | active | 当前项目（源码+data 配置）打包 → Linux 服务器运行（Python 3.12 via uv、systemd 守护） | 验收标准 1、2、6 |
| Nginx 域名接入 | active | yuansheng.tudodo.vip 按服务器现有 conf.d 模式追加 server 块，整域 http 反代 AstrBot 6185 | 验收标准 3 |
| 企微回填 | active | 企微管理后台：自建应用创建、回调 URL/Token/AESKey 保存（GET 验证）、可信 IP、微信客服 API 授权 | 验收标准 4 |
| 端到端联调验收 | active | 客户微信进客服会话 → 琴行知识库 RAG → DeepSeek 回复，无需唤醒词前缀 | 验收标准 4、5、6 |
| 转人工+邮件通知插件 | deferred | 指引阶段 D（关键词转人工 + SMTP 邮件通知）| 用户确认不在本轮范围（2026-10-01），作为下一轮任务 |

## Goal
把当前定制项目 `D:\tjs\tys\AstrBot`（dev 分支，v4.28.1，已含琴行示例知识库/DeepSeek+DashScope 配置）打包部署到腾讯云服务器 124.222.113.7，通过 nginx 以 yuansheng.tudodo.vip 整域 http 反代对外，完成企业微信自建应用回调回填，实现：客户在微信进入客服会话 → AI 基于琴行知识库自动回复，全流程可由店主扫码实测验收。

## Constraints
- **部署方式：Docker 容器**（用户指定，遵循 `C:/Users/oyl/.zcode/workspace/default/docker-deploy-guide.md`）：本地 Docker Desktop 构建 → `docker save | gzip` → scp → 服务器 `docker load` → compose 运行；服务器 Docker 29.8.2 + Compose v5.5.1 已装好并开机自启（2026-10-01 实测复核，当前零容器）。数据卷挂载在容器外（指南 §7.2：数据不能只在容器里）
- nginx 已有 conf.d 按域名转发模式（`server_name *.tudodo.vip → proxy_pass 127.0.0.1:xxxx`），只追加不重构；全站 http:80、无 SSL 证书 → 本次走 http（企微回调不强制 https）
- `data/` 不入 git → 打包必须显式携带本地 data/；服务器上 AstrBot 只监听 127.0.0.1:6185（不直接暴露公网，仅经 nginx）
- 唤醒词 `AI`（`friend_message_needs_wake_prefix=true`）对微信客服会话同样生效 → 服务器配置必须关闭，否则客户须打"AI"前缀才触发回复
- 本地 `weixin_oc`（微信个人号）平台在服务器无运行环境 → 服务器配置中禁用/移除
- 企微侧仅"微信客服账号已建"：自建应用未创建（回调无挂载点，需用户人工创建）、企业未认证（累计接待 100 客户上限，不阻塞打通，列为上线限制）
- 不修改 `D:\tys\AstrBot` 本地实例与 CowAgent 项目（指引 §2/§7 红线，虽然本方案改用当前项目部署，红线仍有效）
- 遵循 CUSTOM_DEV_GUIDE：定制走 data/ 配置，不改 `astrbot/core` 核心代码；本次不改仓库源码，只部署

## Non-Goals
- 转人工 + 邮件通知插件（阶段 D，下一轮）
- 聊天记录导出脚本（阶段 E）
- HTTPS 证书配置（结构上预留，后续可加）
- 真实商品资料上传（示例琴行知识库验收通过后，店主自行在 WebUI 替换）
- 修改指引文档中 `D:\tys\AstrBot` 实例相关内容（该实例角色另行处理）

## Acceptance Criteria
- [ ] 1. 服务器上容器 `yuansheng-astrbot` 以 `restart: unless-stopped` 运行，AstrBot 经端口映射监听宿主机 127.0.0.1:6185；宿主机/容器重启后自动拉起
- [ ] 2. 镜像含 dev 分支源码（v4.28.1 定制版）；数据卷含 cmd_config.json 修改版（wecom 平台+关唤醒词、无 weixin_oc）、knowledge_base/ 琴行库、data_v4.db、dist/ WebUI 资源
- [ ] 3. `http://yuansheng.tudodo.vip` 公网可访问 AstrBot WebUI（nginx 整域反代，支持 websocket/SSE）
- [ ] 4. 企微后台保存回调配置时 GET echostr 验证通过；客户发消息后服务器日志出现 `kf_msg_or_event` 回调 → sync_msg 拉取 → RAG/LLM 调用 → 发送回复
- [ ] 5. 客户任意消息（不以"AI"开头）即触发自动回复（唤醒词已在该部署关闭）
- [ ] 6. 店主微信扫码进入客服会话，问"钢琴课多少钱一节？"，收到基于琴行知识库的 RAG 回复（终验，真人执行）

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 指引文档假设部署实例是 `D:\tys\AstrBot` | 用户明确"使用当前项目"（cwd = `D:\tjs\tys\AstrBot` 定制 fork） | 以当前项目为部署源；指引中本地实例章节作废，其余（企微流程/硬约束/源码路径）继续有效 |
| 转人工插件是"核心开发任务"可能要在本轮做 | 拓扑确认时正面询问 | 本轮只做部署+打通，插件下一轮 |
| 企微侧前置条件可能已就绪 | 逐项多选确认 | 仅微信客服账号已建；自建应用创建列为用户人工前置步骤；未认证的 100 客户上限列为已知限制 |
| 服务器可能已具备 Python 3.12 / docker | SSH 实测 | 均无；用 uv 装独立 3.12 |
| 回调需要 https | 服务器无证书且现有站点全 http；企微回调不强制 https | 整域 http 反代，后续可加证书 |
| 验收可能等真实资料 | 访谈确认 | 用现有示例琴行知识库验收 |

## Technical Context（代码库与服务器实测事实）

### 代码库（`D:\tjs\tys\AstrBot`，dev 分支，v4.28.1）
- **wecom 适配器**：`astrbot/core/platform/sources/wecom/wecom_adapter.py`
  - `kf_name` 非空 → 微信客服模式（wecom_adapter.py:208-214）
  - 回调两种模式：统一 webhook（默认，`unified_webhook_mode=true`，平台加载时自动生成 `webhook_uuid`，走主端口 6185，路径 `/api/platform/webhook/{uuid}`，manager.py:93 / webhook_utils.py:58）或独立端口（默认 6195，路径 `/callback/command`，wecom_adapter.py:76-85）。**本次用统一 webhook 模式**（与 WebUI 同端口，nginx 只需反代一个上游）
  - 配置字段（default.py:423-437）：`corpid`、`secret`、`token`、`encoding_aes_key`、`kf_name`、`unified_webhook_mode`、`webhook_uuid`
  - `kf_name` 是**客服账号的名称**（非 open_kfid）：启动时调 get_account_list 按名称匹配解析 open_kfid（wecom_adapter.py:310-323），并自动打印客服二维码链接（:327-337，联调扫码入口）；`secret` 在适配器构造即用于 WeChatClient（:202-205），必须为真实值才能通过 API 拉取/发送消息
  - `send_by_session` 在 kf 模式不支持主动发送（48h 窗口硬约束仍在）
- **唤醒词**：`astrbot/core/pipeline/waking_check/stage.py:152-158`——wecom kf 消息是 FRIEND_MESSAGE（wecom_adapter.py:427-436），仅 webchat 平台豁免唤醒词；本地配置 `wake_prefix=["AI"]` + `friend_message_needs_wake_prefix=true` 会要求客户打"AI"前缀
- **data/ 现状**（不入 git）：端口 6185；平台仅 `weixin_oc`（服务器须禁用）；provider：DeepSeek ×2（对话）+ `dashscope_kb/text-embedding-v4`（embedding）均已配好，密钥随 data/ 携带；`kb_names: ["悦音琴行知识库"]`；`data/knowledge_base/`（kb.db + 集合目录含 faiss 索引）；`data/dist/`（WebUI 静态资源已存在，服务器无需下载/构建）
- **启动依赖**：pyproject `requires-python>=3.12`；uv.lock 已跟踪；端口取 `dashboard.port`（server.py:634-637），host 取 `dashboard.host`（默认 0.0.0.0，服务器上改 127.0.0.1）

### 服务器（124.222.113.7，SSH 实测 2026-10-01）
- OpenCloudOS 9.4；**Docker 29.8.2 + Compose v5.5.1 已装好、active、开机自启**（当前零容器运行）；`/root/images`、`/root/apps` 尚未创建
- 本地 Docker Desktop 4.93.0（Engine 29.8.1）运行中，x86_64 两端一致无需跨平台构建
- 宝塔面板在跑（8888，勿动）；nginx 1.26.3，`/etc/nginx/conf.d/` 模式：gomoney.conf / tudodo-server.conf / usercollect.conf（.bak 备份文件同在）；追加 `yuansheng.conf` 即可
- `yuansheng.tudodo.vip` 与 `tudodo.vip` 均已解析到本机；80 端口已对外服务（子域名站点正常，备案无阻）
- 端口 6185/6195 空闲；内存 3.6G（可用 2.8G）、磁盘余 30G——足够
- 已有服务：uvicorn 8601（tudodo-server）、uvicorn 127.0.0.1:8090（usercollect）——均勿动

### 架构（目标态，Docker 部署）
```
客户微信 → 微信客服(企微) → 回调POST → nginx:80 (yuansheng.tudodo.vip)
                                        → proxy_pass 127.0.0.1:6185 (仅本机回环)
                                          → 容器 yuansheng-astrbot (publish 127.0.0.1:6185:6185)
                                            → /api/platform/webhook/{uuid} (统一webhook)
                                              → sync_msg 拉取 → 琴行KB RAG + DeepSeek → 回复客户
数据持久化: /root/apps/yuansheng-astrbot/data (volume 挂载 /AstrBot/data, 升级换镜像不丢数据)
WebUI 管理台: http://yuansheng.tudodo.vip/ (同一域名同一端口, 密码登录)
```

## Implementation Plan（执行顺序，含验证点；部署方式遵循 docker-deploy-guide.md）

### 凭据与物料清单（源码核实：wecom_adapter.py:202-214/310-337）
| 凭据/物料 | 来源 | 谁准备 | 时机 | 状态 |
|---|---|---|---|---|
| CorpId（企业ID，ww开头） | 企微后台 → 我的企业 → 企业信息 | **用户提供** | 现在即可 | ✅ `ww991771f6514a8a43`（缘声琴行，未认证） |
| 自建应用 Secret | 企微后台 → 应用管理 → 自建（**用户先创建应用**） | **用户提供**（或 WebUI 自填） | 现在即可（建应用后） | ⏳ 用户创建应用中 |
| 客服账号名称（kf_name） | 已建微信客服账号的名称，须与后台完全一致 | **用户提供** | 现在即可 | ⏳ 客服账号已建，账号 id `kfc57a244017f053251`，名称待确认 |
| Token / EncodingAESKey | 回调验签加密，两端一致即可 | **我生成**（随机，符合企微规范） | 部署时 |
| 回调 URL | `http://yuansheng.tudodo.vip/api/platform/webhook/{uuid}`，uuid 由 AstrBot 生成后从服务器读出 | **我拼好给用户** | 部署后 |
| DeepSeek / DashScope Key | 已在本地 `data/cmd_config.json` | 随数据卷携带，**无需动作** | — |

### 阶段 1：本地构建镜像 → 验证：docker build 成功、镜像大小合理
1. 前提检查：本地 `docker version` 正常（虚拟化报错则重启电脑，指南 §1）；工作区干净、以 dev 分支为准
2. 核查仓库 `Dockerfile` 与 `.dockerignore`（确保排除 data/、.git、dashboard/node_modules；必要时本地修正 .dockerignore）
3. `docker build -t yuansheng-astrbot:1.0.0 .`
4. `docker save yuansheng-astrbot:1.0.0 | gzip > 部署目录/yuansheng-astrbot-1.0.0.tar.gz`

### 阶段 2：服务器运行 → 验证：容器 healthy、curl 127.0.0.1:6185 返回 WebUI
1. scp 镜像包到 `/root/images/`（先建目录）；`docker load < ...tar.gz`
2. 准备 `/root/apps/yuansheng-astrbot/`：
   - `docker-compose.yml`：image `yuansheng-astrbot:1.0.0`、`restart: unless-stopped`、`ports: "127.0.0.1:6185:6185"`（只绑回环，不暴露公网，免防火墙变更）、`volumes: ./data:/AstrBot/data`、`TZ=Asia/Shanghai`
   - `data/`：本地 data/ 关键项上传——`cmd_config.json`（**修改 2 处**：① 禁用/移除 weixin_oc 平台、新增 wecom 平台（corpid/secret/token/encoding_aes_key/kf_name/unified_webhook_mode=true）② `platform_settings.friend_message_needs_wake_prefix` → false；host/port 不变，容器内 0.0.0.0:6185，由 ports 映射收敛到回环）、`knowledge_base/`（kb.db 与集合目录，含 -wal/-shm 一起拷）、`data_v4.db`（含 -wal/-shm）、`dist/`（WebUI 静态资源）
3. `docker compose up -d`，`docker compose logs` 确认平台加载无致命错误（首次可无 corpid/secret 先跑通 WebUI，企微凭据到位后填入重启）

### 阶段 3：nginx 追加 → 验证：公网 curl 通过、nginx -t 干净
1. 新建 `/etc/nginx/conf.d/yuansheng.conf`：listen 80、server_name yuansheng.tudodo.vip、proxy_pass http://127.0.0.1:6185、`proxy_http_version 1.1` + websocket Upgrade 头 + 适当超时
2. `nginx -t && systemctl reload nginx`

### 阶段 4：企微回填（我供值 + 用户人工）
1. 我生成 Token（随机串）与 EncodingAESKey（43 位）写入服务器 wecom 配置，读出 `webhook_uuid`，拼出回调 URL：`http://yuansheng.tudodo.vip/api/platform/webhook/{uuid}`，重启服务
2. **用户人工步骤清单**（指引阶段 C）：
   a. 企微管理后台 → 应用管理 → 创建**专用自建应用**（不复用现有应用）
   b. 把 **CorpId** 和该应用的 **Secret** 准备好（Secret 可直接发我，或自行在 WebUI 平台配置页填写——二选一，默认用户自填）
   c. 自建应用 → 接收消息 → 设置 API 接收：粘贴我给的 URL / Token / EncodingAESKey → 保存（此时触发 GET 验证，AstrBot 必须在线，我负责盯日志）
   d. 应用详情页 →「企业可信IP」加入 **124.222.113.7**
   e. 微信客服 → API → 「可调用接口的应用」勾选该自建应用
   f. 「通过API管理微信客服账号」→ 选择交给机器人接管的客服账号
   g. （可选，下轮转人工要用的前置）把店主企微号加为该客服账号接待人员
3. 已知限制告知：未认证企业累计只能接待 100 位客户（¥300/年认证后解除，用户后续自行决定）

### 阶段 5：联调验收 → 验证：验收标准 4/5/6
1. 我：日志验证回调 GET echo 通过、用户测试消息的 sync_msg→RAG→回复全链路
2. 用户：微信扫码客服链接（微信客服后台可生成）→ 问"钢琴课多少钱一节？" → 收到琴行知识库 RAG 回复 → **终验通过**
3. 复核：消息不以"AI"开头也触发（唤醒词已关）；容器重启后服务自动恢复；客服二维码链接可从启动日志获取（wecom_adapter.py:336 会打印扫码链接，作为联调入口）

### 风险与对策
- 本地 Docker Desktop 未启动/虚拟化报错 → 重启电脑（指南 §1）；执行前先 `docker version` 自检
- 回滚预案（指南 §7.6）：旧 tar.gz 保留在 /root/images/，出问题 `docker load` 旧包 + compose 改回版本号即可；服务器写操作前先备份（cp xxx xxx.bak-$(date +%F)）
- SQLite 热拷贝（data_v4.db / kb.db）→ 连同 -wal/-shm 三个文件一起拷；若本地实例正在跑，择其空闲时刻
- 企微保存回调时 GET 验证失败 → 先 `curl -I` 公网 URL、查容器日志验签报错；Token/AESKey 必须与后台完全一致
- API 调用报 60020 → 可信 IP 未加或未生效
- 48h 窗口：客户超 48h 未发消息后机器人主动发送会失败（`msg_send_fail`），属预期行为不修
- faiss 索引跨 Windows→Linux 迁移：文件型无路径依赖，风险低；异常时知识库可在 WebUI 重建（源文档在 `kb_docs/`）
- WebUI 公网 http 暴露：密码策略已有强制（≥8 位大小写数字）；提醒店主用强密码，后续可加 https

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| AstrBot 云实例 | 部署单元 | /opt/yuansheng-astrbot、systemd、127.0.0.1:6185 | 承载 wecom 渠道与 WebUI |
| wecom 平台配置 | 配置实体 | corpid/secret/token/encoding_aes_key/kf_name/webhook_uuid | 挂接微信客服账号 |
| 微信客服账号 | 外部系统 | open_kfid、接待人员 | 回调经自建应用进入 AstrBot |
| 自建应用（企微） | 外部系统 | CorpId、Secret、回调URL、可信IP | 企微回填的操作对象 |
| 回调 URL | 集成点 | http://yuansheng.tudodo.vip/api/platform/webhook/{uuid} | nginx 反代到 AstrBot |
| nginx server 块 | 基础设施 | yuansheng.conf、listen 80、proxy_pass 6185 | 域名唯一入口 |
| 琴行示例知识库 | 数据资产 | kb.db、faiss 索引、kb_docs/ 源文档 | RAG 供源，验收用 |
| 唤醒词配置 | 行为开关 | friend_message_needs_wake_prefix、wake_prefix | 服务器部署须关闭 |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1(拓扑) | 8 | 8 | - | - | N/A |
| 2 | 8 | 0 | 0 | 8 | 100% |
| 3 | 8 | 0 | 0 | 8 | 100% |

## Interview Transcript
<details>
<summary>Full Q&A（Round 0-3）</summary>

### Round 0（拓扑确认）
**Q:** 4 组件拓扑是否正确？转人工+邮件插件是否纳入本轮？
**A:** 拓扑正确，插件不在本轮。
**Ambiguity:** 未评分（拓扑门）

### Round 1（企微现状，Context）
**Q:** 企微侧前置条件哪些已完成？
**A:** 仅"微信客服账号已建"（认证/自建应用/接待人员均未完成）。
**Ambiguity:** 29% (Goal 0.85, Constraints 0.60, Criteria 0.60, Context 0.75)

### Round 2（暴露策略，Constraints）
**Q:** nginx 暴露策略选哪种？
**A:** 整域反代 http。
**Ambiguity:** 23% (Goal 0.85, Constraints 0.80, Criteria 0.60, Context 0.80)

### Round 3（验收标准，Criteria）
**Q:** "打通全流程"的验收标准怎么定？
**A:** 示例琴行知识库验收（部署后扫码问"钢琴课多少钱"，收到 RAG 回复即通过）。
**Ambiguity:** 13% (Goal 0.90, Constraints 0.85, Criteria 0.85, Context 0.85)
</details>

---

## 验收结果（2026-10-01 17:29 实测通过）

- [x] 1. 容器 `yuansheng-astrbot` 运行中（restart: unless-stopped，127.0.0.1:6185，重启自动拉起）
- [x] 2. 镜像 dev 源码 + 数据卷（配置/琴行知识库/人格/聊天库/WebUI）完整
- [x] 3. `http://yuansheng.tudodo.vip` 公网可访问（nginx 追加式配置，备份于 /root/nginx-conf.d.bak-*）
- [x] 4. 企微回调 GET 验证通过；消息链路日志：`kf_msg_or_event` → sync_msg → RAG/LLM → send（17:29:36 收到 → 17:29:39 回复，<3 秒）
- [x] 5. 客户消息无唤醒词前缀即触发
- [x] 6. 终验（真人扫码）：微信发"吉他试听课怎么收费" → 回复"试听课统一49元一节，45分钟一对一🎸 试听后7天内报名任意课程，这49元可以全额抵扣学费…"（知识库+人格均正确命中）

### 实施中的关键发现（补充记录）
- **企微微信客服双形态**：kf.weixin.qq.com 独立版建号后须在企微后台微信客服应用点「开始使用」启用联合版，否则自建应用 Secret 调 kf/* API 报 95012（not use in wecom）
- **客服账号真实名称「缘声琴行客服」**（kf_name 须与 API 返回 name 完全一致）；open_kfid `wkQcA1OAAA8RMMr9MXhw5Cm-hh-sQEAQ`（显示后缀 @缘声琴行 对应旧账号 id kfc57a244017f053251）
- AstrBot 未实现 enter_session 欢迎语事件（WARN 无碍主链路；欢迎语可在阶段 D 一并做）
- 部署产物：镜像 `yuansheng-astrbot:1.0.0`（tar 留 /root/images/ 可回滚）；服务器目录 /root/apps/yuansheng-astrbot/；配置修改均已留 .bak
