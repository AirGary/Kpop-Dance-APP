# Stage Lab 项目状态

## 项目名称与目标

Stage Lab 是面向 K-pop 翻跳学习者的 iPhone 练习 App。当前最高优先级是先完成一个真实人物检测、目标追踪、姿态与动作分解的可体验 AI Demo，再逐阶段迁移云端并扩展为可上架商品。

## 当前可运行状态

- SwiftUI App 可在 iOS 26.5 Simulator 编译、运行和完成首页冷启动测试。
- 本地导入、视频副本、播放练习、本地 FastAPI、可恢复上传客户端和 Demo 分析界面已存在。
- Google Cloud Stage 5B 基础已于 2026-07-16 部署到 `stage-lab-dev-gary-202607` 的新加坡区域。
- 线上 API：`https://stage-lab-api-rf222fhruq-as.a.run.app`。
- 线上 `/health` 返回 `{"status":"ok","environment":"cloud"}`；开发令牌访问受保护接口返回 `401`。
- 目前没有真实 AI Worker、GPU、人物检测、姿态分析或音乐分段服务，App 中的分析结果仍不能视为真实 AI 结果。

## 当前阶段与状态

**阶段：Stage 5B 云端数据基础已完成；Stage 6 本地真实 AI 动作分解闭环已完成产品设计确认，实施尚未开始。**

用户决定测试版 Demo 暂不实现任何面向用户的账号登录，并将下一阶段改为本地真实 AI 最小闭环。Stage 6 先在 Mac 运行真实 Worker，用一条 `82MAJOR Trophy` 视频完成“检测候选舞者 -> 用户选人 -> 目标追踪与骨架 -> 动作分段 -> App 成品播放器”的闭环；本地验收后再迁移同一 Worker 到 Google Cloud。

### 阶段范围

- 包含：本地 FFprobe/FFmpeg、RTMDet、ByteTrack、RTMPose、基础节拍、真实候选舞者、目标聚光、可开关骨架、动作时间轴、结果包校验与离线练习。
- 不包含：Sign in with Apple 或其他用户登录、云端 GPU、音乐语义段落、大模型教学文案、付费、APNs、CloudKit。
- 首轮样本：用户已有的 `82MAJOR Trophy` 视频；通过后再扩大到 3 条和 20 条基准视频。
- 设计文档：`docs/superpowers/specs/2026-07-16-stage-6-local-real-ai-vertical-slice-design.md`。

### 阶段开始确认记录

- 2026-07-16：用户明确确认“完成并部署云端基础”。
- 成本边界：Cloud Run 最小实例 0、最大实例 1、1 CPU、512 MiB；不创建 GPU；预算 JPY 1,000/月，仅发送告警，不是硬停机上限。
- 2026-07-16：用户确认采用低成本 Firebase Authentication 初始化方案；不开启邮箱、手机或匿名登录，仅使用两个临时 Custom Auth 身份完成隔离测试。Identity Platform 初始化不可删除，已采用 Terraform `prevent_destroy` 防止误操作。
- 2026-07-16：用户要求测试版 Demo 暂不加入账号登录，把真实舞蹈视频 AI 分析和动作分解成品形态设为最高优先级。
- 2026-07-16：用户确认本地 Worker 优先方案、单视频验收、两阶段分析、聚光 + 可开关骨架 + 时间轴、基础节拍范围、结果格式、错误恢复与回退边界。

## 已完成阶段

- Stage 0：iOS 工程基线。
- Stage 1：本地域模型与项目持久化基础。
- Stage 2：本地 FastAPI、所有权隔离和稳定 API 合约。
- Stage 3：iOS 本地 API 接入。
- Stage 4：本地视频压缩、断点续传和上传恢复。
- Stage 5A：Cloud Run 与 Artifact Registry bootstrap。
- Stage 5B：Firebase Auth、Firestore、私有 Storage、真实双身份隔离与成本门禁。

## 最近完成任务

### Task：Stage 6 本地真实 AI 闭环产品设计（待书面规格验收）

**目标：** 固定首个真实 AI 成品范围与实施边界，避免账号和云部署继续阻塞 AI 验证。

- [x] 确认不在测试版加入面向用户的账号登录。
- [x] 确认先在 Mac 本地运行真实 AI Worker，再迁移 Google Cloud。
- [x] 确认两阶段流程：真实候选舞者后再分析一名目标舞者。
- [x] 确认成品播放器为聚光跟随、可开关骨架和动作时间轴。
- [x] 确认首版只做 BPM、节拍和强拍，不做音乐语义段落。
- [x] 确认首条 `82MAJOR Trophy` 视频的验收指标与回退方案。
- [ ] 用户验收仓库内书面设计规格。
- [ ] 编写并验收实施计划。
- [ ] 开始测试先行实施。

### Task：完成 Stage 5B 部署后收敛与验证（已验收）

**目标：** 消除 Terraform 假漂移并完成真实身份隔离验证。

**Subtask 1：Cloud Run scaling 漂移修复**

- [x] 复现部署后 `terraform plan`：`0 add / 1 change / 0 destroy`。
- [x] 确认根因是 Google API 自动回填服务级 `scaling=0`，实际模板级 `min=0/max=1` 未改变。
- [x] 添加失败契约测试，要求 Terraform 忽略该 Provider 默认字段。
- [x] 实现最小 Terraform 修复并使测试通过。
- [x] 针对真实云 state 执行只读 `terraform plan`，结果为 `No changes`、退出码 0；无需 apply。
- [x] 修复提交 `57a7554` 已由 PR #2 合并。
- [x] 用户合并后，从主分支再次确认 `terraform plan -detailed-exitcode` 返回 0。

**Subtask 2：真实双身份冒烟测试**

- [x] 确认低成本测试方案与不可删除配置风险。
- [x] 在 Terraform 中加入 Firebase Authentication 初始化配置，并显式关闭 Email、Phone、Anonymous 登录。
- [x] 审查并应用只新增 Identity Platform 配置的 Terraform plan：`1 added / 0 changed / 0 destroyed`。
- [x] 显式设置 Terraform quota project，并锁定 `multi_tenant.allow_tenants=false`；部署后 plan 为 `No changes`。
- [x] Auth 初始化配置提交 `420493d` 已由 PR #3 合并。
- [x] 创建两个临时 Custom Auth 测试身份。
- [x] 使用两个不同 Firebase ID Token 运行 `cloud-bootstrap.sh smoke`。
- [x] 删除临时测试用户并确认没有残留测试任务或签名权限。
- [x] 验证用户 A 创建记录、用户 B 获得同一 `404`、用户 A 删除后再次 GET 为 `404`。

## 数据流、API 与存储位置

1. iPhone 在本地校验并生成最高 1080p 的上传副本，原视频仍保存在 App 本地。
2. App 使用 Firebase ID Token 调用 Cloud Run `/v1/uploads` 和 `/v1/jobs`。
3. Cloud Run 将上传与任务元数据写入 Firestore，不转发视频字节。
4. App 通过私有 GCS resumable session 直接上传到 Source Bucket。
5. Source Bucket 对象 1 天后清理；Result Bucket 对象 7 天后清理；Firestore `uploads.ttlExpiresAt` TTL 已为 `ACTIVE`。
6. 后续 AI Worker 将读取 Source Bucket，写入 Result Bucket；App 下载 Analysis Package 后保存到本机。

## 技术栈与架构摘要

- iPhone：SwiftUI、SwiftData、AVFoundation、Swift Concurrency。
- API：Python 3.13、FastAPI、Pydantic、Firebase Admin SDK。
- 云端：Cloud Run、Firestore、Cloud Storage、Artifact Registry、Terraform。
- 当前容器：`sha256:3a933b0562e8aaa10b0981e12f35a90f3449b5282a60ea0019ce2b1fe3d68f58`。
- AI 规划：FFmpeg/FFprobe、RTMDet、ByteTrack、Re-ID、RTMPose 和音乐节拍分析；尚未部署。

## 测试与验证记录

### 2026-07-16 本地与部署前

- `./scripts/verify-backend.sh`：146 项通过，0 失败。
- `./scripts/verify-ios.sh`：iOS 单元测试、UI 冷启动、Staging 和 Release Simulator 构建通过。
- `terraform validate` 与 `terraform fmt -check -recursive`：通过。
- 独立部署门禁复审：P0/P1/P2 均为 0。

### 2026-07-16 真实云环境

- Terraform apply：`12 added / 2 changed / 0 destroyed`。
- Cloud Run：`min=0`、`max=1`、`1 CPU`、`512MiB`、`APP_ENVIRONMENT=cloud`。
- Source Bucket：新加坡、禁止公开、统一访问、软删除 0、1 天 Delete 生命周期。
- Result Bucket：新加坡、禁止公开、统一访问、软删除 0、7 天 Delete 生命周期。
- Firestore TTL：`uploads.ttlExpiresAt` 状态 `ACTIVE`。
- Artifact Registry：7 天清理所有旧版本，同时保留最近 5 个版本；当前约 82.4 MB。
- Cloud Run scaling 假漂移修复验证：`terraform plan -detailed-exitcode` 返回 0，`No changes`，未执行 apply。
- Firebase Authentication：Identity Platform 已初始化；Email、Phone、Anonymous 和 Multi-tenant 均关闭，apply 为 `1 added / 0 changed / 0 destroyed`，部署后 plan 为 `No changes`。
- 双身份 smoke：`health=ok`、无效开发令牌 `401`、`identity_isolation=ok`、Bucket 私有和 Cloud Run 成本门禁通过。
- 清理复核：临时 Firebase 用户 `0`、临时 Firestore 任务 `0`、临时 Token Creator IAM 绑定 `0`。

## 部署环境与成本控制

- 项目：`stage-lab-dev-gary-202607`。
- 区域：`asia-southeast1`。
- 预算：JPY 1,000/月项目专属告警，阈值 10%/50%/80%/100%；预算不是硬上限。
- Cloud Run 空闲缩容到 0，最大 1 个实例；无 GPU、无常驻 Worker。
- Bucket 禁止公开访问，视频和结果分别按 1 天与 7 天清理。
- Artifact Registry 最少保留最近 5 版，超过 7 天的旧版允许清理。

## 已知问题与风险

- **已解决：** Cloud Run 服务级 scaling 假漂移已由 PR #2 合并，并从主分支在真实云 state 上复核为零变更。
- **已解决：** 两个真实 Firebase 临时身份的线上所有权隔离测试通过，测试身份、任务和临时 IAM 授权已清理。
- **不可逆配置，已确认：** Identity Platform 项目配置初始化后不能删除；Terraform 使用 `prevent_destroy`，且本阶段不开放 Email、Phone、Anonymous 登录。
- **产品缺口：** iOS 尚未接入 Sign in with Apple 和生产 Firebase Token，因此当前 App 不能完成正式云端登录上传流程。
- **功能缺口：** 没有真实 AI 分析，当前仅完成云端数据基础。
- **阶段变更：** 用户登录与正式云上传联调已延期；Stage 6 先解决真实 AI 成品闭环。
- **模型风险：** RTMDet/RTMPose 在当前 Apple Silicon 环境的 MPS 算子兼容性和实际速度尚未测量，实施时必须保留 CPU 回退并记录耗时。
- Terraform state 当前只保存在主检出目录本机；丢失会增加基础设施恢复难度，需要后续迁移到受保护的远端 state。

## 下一阶段建议

下一步是验收 Stage 6 书面设计，然后编写测试先行的实施计划。实施顺序从媒体预检和真实候选舞者开始，之后完成目标追踪、姿态、动作规则、Analysis Package 和 App 播放器叠加。Sign in with Apple 延后到外部 TestFlight 或商品级用户隔离前处理。

## 阶段验收记录

- 2026-07-16：用户回复“已合并并验收 Stage 5B”，Stage 5B 正式标记为“已完成”。
- 2026-07-16：用户逐项确认 Stage 6 产品设计；仓库书面规格仍待用户验收。

## 最后更新时间与对应 Git 提交

- 最后更新：2026-07-16（Asia/Tokyo）。
- 已部署 Git 提交：`21161a288e73ebc40a5716b01db1d1f8210037a7`。
- Cloud Run scaling 收敛修复提交：`57a7554`，PR #2 合并提交 `636ed3d`。
- Firebase Authentication 初始化提交：`420493d`，PR #3 合并提交 `59dec60`。
- Stage 5B 真实云验证记录提交：`033db4e`，PR #4 合并提交 `d890ecf`。
- 当前工作分支：`codex/stage6-real-ai-design`（Stage 6 设计与进度记录）。
