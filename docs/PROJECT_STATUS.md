# Stage Lab 项目状态

## 项目名称与目标

Stage Lab 是面向 K-pop 翻跳学习者的 iPhone 练习 App。当前最高优先级是先完成一个真实人物检测、目标追踪、姿态与动作分解的可体验 AI Demo，再逐阶段迁移云端并扩展为可上架商品。

## 当前可运行状态

- SwiftUI App 已在 iOS 26.5 Simulator 目标完成无测试构建；Xcode 26.6 的测试观察器仍会触发 CoreSimulator 服务崩溃，需要后续环境复核。
- 本地导入、视频副本、播放练习、本地 FastAPI、可恢复上传客户端和 Demo 分析界面已存在。
- Google Cloud Stage 5B 基础已于 2026-07-16 部署到 `stage-lab-dev-gary-202607` 的新加坡区域。
- 线上 API：`https://stage-lab-api-rf222fhruq-as.a.run.app`。
- 线上 `/health` 返回 `{"status":"ok","environment":"cloud"}`；开发令牌访问受保护接口返回 `401`。
- 本地真实 AI Worker 已能完成视频预检、RTMDet-m/ByteTrack 候选检测、RTMPose-m 目标姿态、基础动作分段和 Analysis Package 输出；iOS 练习页已消费结果包，当前仍是本地真实 AI Demo，不是完整商品化分析。

## 当前阶段与状态

**阶段：Stage 5B 云端数据基础已完成；Stage 6 Task 8 已完成，Task 9 实现与自动门禁已完成，待用户验收。本轮不启用云端 GPU 或用户登录。**

用户决定测试版 Demo 暂不实现任何面向用户的账号登录，并将下一阶段改为本地真实 AI 最小闭环。Stage 6 先在 Mac 运行真实 Worker，用一条 `82MAJOR Trophy` 视频完成“检测候选舞者 -> 用户选人 -> 目标追踪与骨架 -> 动作分段 -> App 成品播放器”的闭环；本地验收后再迁移同一 Worker 到 Google Cloud。

### 阶段范围

- 包含：本地 FFprobe/FFmpeg、RTMDet-m、ByteTrack、RTMPose-m、基础节拍、真实候选舞者、目标聚光、可开关骨架、动作时间轴、结果包校验与离线练习。
- 不包含：Sign in with Apple 或其他用户登录、云端 GPU、音乐语义段落、大模型教学文案、付费、APNs、CloudKit。
- 首轮样本：用户已有的 `82MAJOR Trophy` 视频；通过后再扩大到 3 条和 20 条基准视频。
- 设计文档：`docs/superpowers/specs/2026-07-16-stage-6-local-real-ai-vertical-slice-design.md`。

### 阶段开始确认记录

- 2026-07-16：用户明确确认“完成并部署云端基础”。
- 成本边界：Cloud Run 最小实例 0、最大实例 1、1 CPU、512 MiB；不创建 GPU；预算 JPY 1,000/月，仅发送告警，不是硬停机上限。
- 2026-07-16：用户确认采用低成本 Firebase Authentication 初始化方案；不开启邮箱、手机或匿名登录，仅使用两个临时 Custom Auth 身份完成隔离测试。Identity Platform 初始化不可删除，已采用 Terraform `prevent_destroy` 防止误操作。
- 2026-07-16：用户要求测试版 Demo 暂不加入账号登录，把真实舞蹈视频 AI 分析和动作分解成品形态设为最高优先级。
- 2026-07-16：用户确认本地 Worker 优先方案、单视频验收、两阶段分析、聚光 + 可开关骨架 + 时间轴、基础节拍范围、结果格式、错误恢复与回退边界。
- 2026-07-16：用户确认并合并 Stage 6 书面规格，允许进入实施计划阶段；尚未安装 AI 依赖或修改产品代码。
- 2026-07-16：用户确认首版模型基线为 RTMDet-m + ByteTrack + RTMPose-m；接口必须可替换，Analysis Package 保持稳定，实施前核对代码与权重商业许可证，首版不使用 VideoMAE 或视频大模型替代逐帧追踪。
- 2026-07-16：用户回复“已合并并确认实施计划”，Stage 6 正式进入实施；首个执行范围仅为 Python 3.11、FFmpeg、模型来源/许可证和单帧真实推理门禁，不启用云 GPU、不改产品 UI。
- 2026-07-17：用户回复“已合并验收记录，确认开始 Task 2”，允许实现本地分析状态/DTO、原子文件仓库、owner/job 隔离工作区和 Job compare-and-set；不读取真实视频内容、不运行 AI、不修改 iOS UI、不创建云资源。
- 2026-07-17：用户回复“PR #11 已合并，确认开始 Task 3”；PR #11 合并提交 `72da1c4` 已核实。Task 3 仅实现合成素材驱动的 FFprobe 媒体预检和最高 720p/30fps、只降不升的 FFmpeg 分析代理；不读取用户视频、不运行人物模型、不修改 iOS、不创建云资源。

## 已完成阶段

- Stage 0：iOS 工程基线。
- Stage 1：本地域模型与项目持久化基础。
- Stage 2：本地 FastAPI、所有权隔离和稳定 API 合约。
- Stage 3：iOS 本地 API 接入。
- Stage 4：本地视频压缩、断点续传和上传恢复。
- Stage 5A：Cloud Run 与 Artifact Registry bootstrap。
- Stage 5B：Firebase Auth、Firestore、私有 Storage、真实双身份隔离与成本门禁。
- Stage 6 Task 1：本地 AI 隔离运行环境、模型/依赖供应链门禁与真实单帧推理。
- Stage 6 Task 2：持久化分析合约、owner/job 隔离工作区、原子文件仓库与 Job compare-and-set。
- Stage 6 Task 3：确定性媒体预检与最高 720p/30fps、只降不升的原子分析代理。
- Stage 6 Task 4（代码部分）：RTMDet-m 可替换检测器适配器、ByteTrack 风格多人关联、候选排序、归一化摘要和代表图发布 Worker。
- Stage 6 Task 5：本地 FastAPI 两阶段编排、持久 Job 仓库、上传完成到候选列表、重启恢复和目标选择幂等键。
- Stage 6 Task 6（代码部分）：iOS 真实分析 API 客户端、轮询状态模型、候选舞者选择、代表图安全 URL、目标选择幂等键和结果元数据落盘字段。

### 当前进行中的任务

#### Task：Stage 6 Task 4 真实候选舞者（真实样本门禁已通过）

- [x] 纯逻辑测试覆盖短时遮挡、时间单调性、归一化框、单帧唯一分配、候选排序和短轨迹过滤。
- [x] 检测器接口隔离 RTMDet-m，输出只包含人物框和置信度；MPS 兼容性错误仅允许一次 CPU 回退。
- [x] Worker 消费 Task 3 代理，按轨迹生成候选摘要，并为可读图像帧写入三张去元数据 JPEG 代表图。
- [x] 使用 `.local-ai` Python 3.11 环境和用户指定的 `82MAJOR Trophy` 视频运行真实检测门禁：6 个候选、6 组代表图完整、分析代理生成成功；结果仅保存在 `/tmp`。
- [x] 完成 Worker 全量回归、模型设备/耗时/候选数量记录，并将采样策略和结构化 runner 输出提交到 Task 5 PR。

当前验证：Task 4 聚焦测试 6 项通过；`./scripts/verify-local-ai.sh` 为 77 项通过，RTMDet-m/RTMPose-m CPU 探针通过；真实视频预检检测耗时约 4 分钟，使用每 6 帧采样，候选数 6，代表图完整率 6/6。

#### Task：Stage 6 Task 5 FastAPI 两阶段分析编排（真实候选联调已通过）

- [x] `local-ai` 环境接入本地工作区、上传完成回调、候选/目标/结果四个接口和受保护结果内容路径。
- [x] 本地 runner 使用独立 `.local-ai/venv/bin/python` subprocess；worker 异常进入 `failedRecoverable`，不把上传请求误报为 500。
- [x] API 与状态机测试、OpenAPI 合约和标准后端回归通过。
- [x] 使用真实 `.local-ai` 环境和 `82MAJOR Trophy` 视频返回 3 个以上候选和三张代表图。
- [x] 实现 `resume_pending()` 的检测/目标队列恢复、持久 Job 状态和目标选择幂等键。
- [x] 真实 FastAPI smoke 完成上传、候选查询、重启后候选恢复和目标选择提交；耗时 280.18 秒。
- [x] 目标姿态、动作分段和结果包由 Task 7 实现，不在 Task 5 验收范围内；Task 7 已完成本地实现，待用户验收。

当前验证：`./scripts/verify-backend.sh` 为 203 项通过、1 项真实视频 smoke 默认跳过；Worker 测试和 `./scripts/verify-local-ai.sh` 均为 77 项通过；真实 API smoke 为 1 项通过。

#### Task：Stage 6 Task 6 iOS 真实分析接入（代码已实现，待 Xcode 运行验收）

- [x] Swift DTO 与 HTTP 请求覆盖候选、目标选择、结果元数据、Bearer/配对令牌和相对路径安全。
- [x] 真实轮询状态覆盖检测、候选等待、目标分析、结果就绪和可恢复失败。
- [x] 真实分析页不再提供手动跳过；候选舞者页在真实任务下显示服务端候选和代表图，Fake/Preview 仍保留静态演示路径。
- [x] SwiftData 增加可选的目标候选 ID、结果 SHA-256 和结果字节数，不保存候选图字节。
- [ ] 在 CoreSimulator 服务恢复后运行 `./scripts/verify-ios.sh`，并联调本地 FastAPI Task 5 端点。
- [x] Task 6 实现已由 GitHub PR #15 合并到 `main`；Xcode 26.6 Simulator 无测试构建通过。
- [ ] Xcode 26.6 `xcodebuild test` 会触发 CoreSimulator 服务断开；PR #16 为兼容性修复，等待用户合并。

#### Task：Stage 6 Task 7 目标姿态、动作分段与 Analysis Package（已完成）

- [x] Task 7 范围确认：RTMPose-m 目标姿态、聚光轨迹、基础节拍、可解释难度、重复组和离线结果包。
- [x] 姿态帧、时间轴、基础节拍和结果包不变量测试通过；结果包使用固定成员、成员哈希和原子发布。
- [x] Worker `target` 从占位错误升级为真实 RTMPose-m 目标分析，并按模型清单 SHA-256 门禁加载权重。
- [x] 使用 `82MAJOR Trophy` 选定舞者生成并校验有效 `result-v1.zip`，包含 17 个姿态帧、17 个聚光关键帧和 5 个练习片段。
- [x] 真实 FastAPI smoke 使用包含舞者的 32 秒视频片段，完成上传、候选列表、重启恢复、选择舞者、`resultReady` 和结果 ZIP 下载。
- [x] 本地 AI 回归 86 项通过；后端相关回归 202 项通过；真实 FastAPI smoke 1 项通过（33.37 秒）。
- [ ] 当前真实门禁使用 `--frame-stride 30` 低成本采样；完整 30fps 目标精度、身份确认和 iOS 结果包渲染留到后续验收。
- [x] iOS 练习页导入和渲染留到 Task 8，不在本轮修改。

#### Task：Stage 6 Task 8 iOS Analysis Package 导入与练习页渲染（已完成）

- 范围：下载并校验 `result-v1.zip`，解析姿态轨迹、聚光轨迹、动作时间轴和置信度，接入现有练习页播放器。
- 不包含：云端 GPU、账号登录、音乐语义分段、完整 30fps 精度和动作纠错。
- 验收：真实 FastAPI 结果可在 iOS 本地保存；练习页能显示目标聚光、骨架开关、动作节点、难度和循环练习；下载失败或结果损坏时有可恢复错误状态。
- 测试：Swift 单元测试、iOS 构建、真实本地 API 联调；Simulator 视频解码问题继续记录，不把模拟器画面当作真实 iPhone 验收。
- 2026-07-21 用户确认开始 Task 8；首个实现范围为无压缩 ZIP 结果包解析、SHA-256/字节数校验、本地原子落盘、练习页真实时间轴、聚光框和骨架开关。
- 2026-07-21：结果包解析/API 下载聚焦 Swift 测试通过；`./scripts/verify-ios.sh` 通过（完整测试、UI 启动、Staging、Release）；后端 `203 passed, 1 skipped`；32 秒真实视频 FastAPI smoke 通过（`1 passed in 32.37s`）。实现提交 `d41ae05`，Draft PR #22 已推送，等待用户审核合并。
- 2026-07-21：真实短片首次目标分析发现 RTMPose 边界点越界，已在姿态适配器增加有限值检查和 `[0,1]` 裁剪，并通过回归测试；不是结果包格式错误。
- 2026-07-21：用户确认 PR #22 已合并；合并提交 `8d637d1af70615c3705765100aadc48bdce809a4`，Task 8 正式验收完成。

#### Task：Stage 6 Task 9 单视频端到端验收与可重复 Demo（进行中）

- 范围：加入本地 AI Demo 一键启动脚本、Simulator/真机配对说明、模型许可证/版本记录、验收记录模板，并把三套验证脚本和真实 82MAJOR 视频验收串成可重复流程。
- 不包含：三视频泛化、云端 GPU 迁移、登录、音乐语义分段、动作纠错、付费和新的 AI 模型。
- 数据流：本机视频 -> 本地 FastAPI -> 独立 Worker -> Analysis Package -> iOS 本地保存与练习页；测试视频、候选图、截图和绝对路径不进入 Git。
- 成本与安全：仅使用本机 CPU/现有模型，不创建云资源；本地服务仅回环或短期私有 LAN 配对，令牌不写入仓库，进程结束即失效。
- 验收：`verify-local-ai.sh`、`verify-backend.sh`、`verify-ios.sh` 全部通过；真实视频完成候选、选人、目标分析、导入、聚光、骨架、低置信度、时间轴、难度/重复、速度、镜像、循环和离线重启检查；记录实际耗时、包大小、限制和未执行项目。
- 当前状态：Task 9 实现和自动门禁已完成，状态为“待验收”；真实视频短片链路通过，等待用户在 Xcode/真机完成视觉和离线产品检查。
- 实际证据：本地 AI `89 passed`，后端 `207 passed, 1 skipped`，iOS 测试及 Staging/Release 构建通过；真实 smoke `1 passed in 31.35s`。完整记录见 `docs/ai/ACCEPTANCE_2026-07-21.md`。
- 2026-07-21 次要联调修补：真实 App 上传、候选和目标分析均成功，但候选图/结果包曾被错误拼接到 API 根路径而返回 `404`；已改为带 Job 作用域和认证头的内容路由，真实 smoke 增加候选图下载验证并通过 `1 passed in 32.61s`。该修补另行提交 PR，未修改用户已有 Xcode 工程改动。
- 2026-07-21 逻辑复查修补：目标舞者一旦选定后禁止切换到另一候选，分析内容路径限制在 Job 的 `analysis/` 目录，iOS 候选页在可恢复失败时显示错误与重试按钮；后端回归 `209 passed, 1 skipped`，iOS Debug Simulator 构建和新增状态测试通过。该修补未修改用户已有 Xcode 工程改动。
- 2026-07-23 代码复查修补：发现 API 返回的稳定内容路径带有 `analysis/` 前缀，但服务端又将它附加到 `analysis/` 目录，导致候选图与结果包被错误解析为 `analysis/analysis/...` 并返回 404。现已把公开内容路径明确为 `analysis/<file>`，服务端仅在验证此前缀后定位到 Job 私有分析目录；新增合法结果包路径与越界路径回归测试。后端完整门禁为 `210 passed, 1 skipped`。
- 2026-07-23：用户确认开始竖屏全身跟随练习页实现。范围仅为 iPhone 17 Pro Max（iOS 26.5）的 iOS 播放渲染：消费既有全身姿态和聚光轨迹，生成 9:16 全身优先裁切，轨迹不可靠时回退完整画面。不会修改模型、Analysis Package schema、后端 API、云资源或 iOS 27 适配。规格为 `docs/superpowers/specs/2026-07-23-portrait-follow-camera-design.md`，实施计划为 `docs/superpowers/plans/2026-07-23-portrait-follow-camera.md`。
- 2026-07-23：竖屏跟随 Task 1 已完成并通过独立代码审查。iOS 26.5 聚焦测试验证 9:16 裁切、全身关键点保留、低置信度/无效/越界/负尺寸轨迹回退，以及异常关键帧不可跨越插值。提交范围仅为纯 Swift 几何与测试；Task 2 开始实现 AVFoundation 真实视频合成。

## 最近完成任务

### Task：Stage 6 Task 3 确定性媒体预检与分析代理（已验收）

**目标：** 为后续人物检测建立可重复、隐私安全的媒体输入门禁，输出固定时间基准且最高 720p/30fps 的 H.264/yuv420p 分析代理，原始素材保持不变。

**Subtask 1：合法合成媒体与失败契约**

- [x] 用 FFmpeg 生成短时测试图案，覆盖高分辨率高帧率、低分辨率低帧率、旋转、无音频、仅音频、损坏字节和超时长元数据。
- [x] 先写稳定错误码、报告字段和代理规格失败测试，不读取用户舞蹈视频。

**Subtask 2：严格媒体预检**

- [x] 使用 argv 调用 FFprobe 并严格解析 JSON、分数帧率和旋转元数据，不经过 shell 插值。
- [x] 拒绝损坏、无视频轨、超过 6 分钟、超过 2 GiB 和非 H.264/HEVC，用户可见错误不包含文件名或绝对路径。

**Subtask 3：只降不升的原子代理**

- [x] 高于规格时降至最高 720p/30fps；540p24 等低规格输入保持尺寸和帧率，不升格。
- [x] 输出 H.264/yuv420p、从零开始的稳定时间基准；失败不留下半成品，成功后重新 FFprobe 验证。

**完成条件：** 媒体聚焦测试、完整 Worker 测试、`verify-local-ai.sh`、后端回归、静态检查和独立代码审查全部通过；更新文档后提交 GitHub。**成本：** 仅本机 CPU/磁盘，云端费用 `0`。**安全风险：** 恶意媒体、路径泄露、shell 注入和半成品代理必须由无 shell argv、稳定错误、超时与原子发布测试阻断。**回退：** 不迁移数据、不修改源视频、不调用云 API；删除生成代理并撤销本分支即可恢复。

实际结果：Task 3 已实现 MP4/MOV/M4V、H.264/HEVC、6 分钟和 2 GiB 门禁，严格解析 VFR 双帧率、旋转、默认视频/音频轨与起止时间。代理只降不升，输出 H.264/yuv420p，并在发布前复核尺寸、帧率、视频和音频完整性。并发发布使用 job 专属目标文件锁和 first-writer-wins；同一目标必须绑定不可变 job/source，后续调用仍预检源文件并返回已验证代理。实现未读取用户视频、未运行人物分析、未修改 iOS/API、未创建云资源。

与原计划差异：为已有 2 GiB 上限新增稳定错误码 `file_size_exceeded`，已同步到实施计划和 README；这是更明确的客户端可处理错误，不改变输入上限。

### Task：Stage 6 Task 2 持久化分析合约与工作区（已验收）

**目标：** 为后续真实媒体预检与人物分析建立可恢复、可隔离、模型无关的数据边界；API 只暴露相对内容路径，不暴露本机绝对路径。

**Subtask 1：稳定 DTO 与状态合约**

- [x] 先写全部状态、候选舞者、目标选择、结果元数据和错误详情的失败测试。
- [x] 实现 Pydantic DTO 与跨端 JSON fixtures，保持 schema version `1`。

**Subtask 2：持久化分析仓库**

- [x] 先写重启恢复、原子替换、owner 隔离、同一 not-found 和路径穿越失败测试。
- [x] 实现 `<OBJECT_STORAGE_ROOT>/<owner>/<job>/analysis/` 下的 JSON 持久化。

**Subtask 3：工作区与 Job 状态转换**

- [x] 先写 hard-link、copy fallback、源文件不变和 compare-and-set 失败测试。
- [x] 实现上传提升与 InMemory/Firestore JobRepository 条件更新。

**完成条件：** 聚焦测试、完整 `verify-backend.sh`、静态差异检查和独立代码审查全部通过；更新文档后提交 GitHub。**成本：** 仅本机 CPU/磁盘，云端费用 `0`。**安全风险：** owner/path 校验错误可能造成越权或路径穿越，必须以相同 not-found 与根目录 containment 测试阻断。**回退：** 本任务不迁移现有数据、不调用云 API，撤销本分支即可恢复。

实际结果：稳定分析 DTO、schema version `1` fixtures、文件型 AnalysisRepository、本地隔离工作区及 InMemory/Firestore Job compare-and-set 已实现。上传提升接口只接收 `owner_id/job_id/upload_id`，源路径由受控根目录推导；发布和 JSON 替换使用唯一临时文件、非覆盖 hard-link 或原子 replace，并对文件及父目录执行持久化同步。Task 2 未增加 API route、未读取真实视频内容、未运行模型、未修改 iOS，也未创建或调用云资源。

### Task：Stage 6 Task 1 本地 AI 运行环境门禁（已验收）

**目标：** 在不污染 Cloud Run API 依赖的前提下，验证 FFmpeg、RTMDet-m 和 RTMPose-m 至少能通过 MPS 或 CPU 完成真实单帧推理。

- [x] 验证现有 backend 与 iOS 基线。
- [x] 先写运行时与模型清单失败测试。
- [x] 建立隔离 Python 3.11 环境与 FFmpeg 前置检查。
- [x] 核对代码、权重来源、SHA-256 与许可证文件。
- [x] 运行真实单帧推理门禁并记录设备、耗时和版本。
- [x] 完整回归和文档更新。
- [x] 提交并推送 GitHub 分支。
- [x] GitHub PR #8 已创建并合并。

实际结果：Python 3.11.15、FFmpeg/FFprobe 8.1.2、PyTorch 2.13.0、MMCV 2.1.0、MMDetection 3.3.0 和 MMPose 1.3.2 已在 macOS 27 arm64 隔离环境安装。RTMDet-m 与 RTMPose-m 对合成单帧真实推理均通过；MPS 未通过整组探针，按设计仅回退一次 CPU。首次冷探针 28.553 秒；两份 checkpoint 均在每次模型加载前重新校验 SHA-256。提交前审查发现的许可证拒绝规则、精确安装约束、空检测结果和过期能力报告问题均已增加回归保护。

### Task：Stage 6 本地真实 AI 闭环产品设计（已验收）

**目标：** 固定首个真实 AI 成品范围与实施边界，避免账号和云部署继续阻塞 AI 验证。

- [x] 确认不在测试版加入面向用户的账号登录。
- [x] 确认先在 Mac 本地运行真实 AI Worker，再迁移 Google Cloud。
- [x] 确认两阶段流程：真实候选舞者后再分析一名目标舞者。
- [x] 确认成品播放器为聚光跟随、可开关骨架和动作时间轴。
- [x] 确认首版只做 BPM、节拍和强拍，不做音乐语义段落。
- [x] 确认首条 `82MAJOR Trophy` 视频的验收指标与回退方案。
- [x] 用户验收仓库内书面设计规格，GitHub 合并提交 `ff2350d`。
- [x] 编写实施计划 `docs/superpowers/plans/2026-07-16-stage-6-local-real-ai-vertical-slice.md`。
- [x] 用户验收实施计划。
- [x] 开始测试先行实施。

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
7. Stage 6 本地 Worker 已通过显式 smoke 读取用户提供的 `82MAJOR` 视频；视频、代理、候选图和结果仅写入 Git 忽略的临时本地工作区，模型、虚拟环境、锁文件和能力报告位于 `.local-ai/`。
8. Task 2 将分析状态和结果 JSON 原子保存在 `<OBJECT_STORAGE_ROOT>/<owner>/<job>/analysis/`；调用者只能使用受校验的 owner、job 和相对内容路径，重启后可从磁盘恢复。
9. 本地上传提升从 `<OBJECT_STORAGE_ROOT>/<owner>/uploads/<upload>/source.mp4` 创建到任务工作区的不可覆盖副本；Job 状态通过 compare-and-set 更新，状态不匹配时不写入。
10. Task 3 对 job 工作区源视频执行 FFprobe 门禁，再在同目录临时文件中生成最高 720p/30fps 代理；完整性复核、文件同步和原子替换成功后才暴露 `proxy.mp4`，失败保留既有有效代理。

## 技术栈与架构摘要

- iPhone：SwiftUI、SwiftData、AVFoundation、Swift Concurrency。
- API：Python 3.13、FastAPI、Pydantic、Firebase Admin SDK。
- 云端：Cloud Run、Firestore、Cloud Storage、Artifact Registry、Terraform。
- 当前容器：`sha256:3a933b0562e8aaa10b0981e12f35a90f3449b5282a60ea0019ce2b1fe3d68f58`。
- 本地 AI 基线：Python 3.11.15、FFmpeg 8.1.2、PyTorch 2.13.0、MMCV 2.1.0、MMDetection 3.3.0、MMPose 1.3.2；媒体预检、720p/30fps 分析代理、RTMDet-m/ByteTrack 候选、RTMPose-m 目标姿态、基础节拍和结果包均已有本地实现。

## 测试与验证记录

### 2026-07-16 本地与部署前

- `./scripts/verify-backend.sh`：146 项通过，0 失败。
- `./scripts/verify-ios.sh`：iOS 单元测试、UI 冷启动、Staging 和 Release Simulator 构建通过。
- `terraform validate` 与 `terraform fmt -check -recursive`：通过。
- 独立部署门禁复审：P0/P1/P2 均为 0。

### 2026-07-16 Stage 6 Task 1

- `.local-ai/venv/bin/python -m pytest backend/workers/analysis/tests/test_runtime_probe.py -q`：26 项通过，0 失败；包含未批准模型/依赖许可证、artifact/模型篡改、空/非有限检测框、精确约束和过期能力报告保护。
- `./scripts/bootstrap-local-ai.sh`：通过；57 个 macOS arm64 artifact 先按 `requirements-macos-arm64.lock` 强制 SHA-256 下载，再从本地目录离线安装。artifact lock SHA-256 为 `9dda16ab9a97d4b366a2557a8a02d920edcccf744d06d8b6f5d0b54eb29e4d05`；许可证清单 SHA-256 为 `b21d11d3995cdcf47c4d3c620008c6aa005b2ff763b35d84a11122f18ba935c5`。
- `./scripts/verify-local-ai.sh`：通过；FFmpeg/FFprobe 8.1.2，RTMDet-m/RTMPose-m `detector_ready=true`、`pose_ready=true`、`device=cpu`，最终复核耗时 5.956 秒。
- `./scripts/verify-backend.sh`：146 项通过，0 失败，1 个既有 Starlette/httpx 弃用警告；Cloud API 环境未安装 torch、MMCV、MMDetection 或 MMPose。
- iOS 基线：单元测试、UI 冷启动、Staging 和 Release Simulator 构建通过；本 Task 未修改 iOS 产品代码。
- 许可证：manifest 在安装前仅接受本阶段已审查的 Apache-2.0 模型；依赖 metadata/随包许可证已完成技术 Demo 审查。`xtcocotools` wheel 内 MIT/BSD 许可证 SHA-256 为 `f96addc34b360737be24174358254ae2c36ab9f757d7810cb52ef5114a25f1cc`；商品发布仍须专项法律复核与 notices 汇总。

### 2026-07-17 Stage 6 Task 2

- 聚焦持久化、工作区、合约与 Firestore CAS 测试：`58` 项通过，`0` 失败。
- `./scripts/verify-backend.sh`：`197` 项通过，`0` 失败，`1` 个既有 Starlette/httpx 弃用警告。
- `git diff --check ee48f5a..HEAD`：通过，无空白错误。
- 初次独立审查发现的任意源路径越权、并发覆盖、固定临时文件冲突、NaN/Inf 和目录持久化风险均已修复并增加回归测试；最终独立复审 `P0/P1/P2` 均为 `0`。
- 本任务未运行 iOS、真实视频、AI 模型或云环境测试，因为改动仅限后端本地持久化边界，未修改相应运行链路。

### 2026-07-17 Stage 6 Task 3

- `.local-ai/venv/bin/python -m pytest backend/workers/analysis/tests/test_media.py -q`：`45` 项通过，`0` 失败；fixtures 全部由 FFmpeg 临时生成，未读取或提交用户视频。
- `./scripts/verify-local-ai.sh`：Worker `71` 项通过，`0` 失败；RTMDet-m/RTMPose-m CPU 探针继续通过，最终探针耗时 `4.876` 秒。
- `./scripts/verify-backend.sh`：`197` 项通过，`0` 失败，`1` 个既有 Starlette/httpx 弃用警告。
- Python `compileall`、fixture/验证脚本 `bash -n` 和 `git diff --check`：通过。
- 三轮独立审查发现的 VFR 绕过、并发报告错配、2 GiB/容器、多流选择、视频/音频完整性、动态超时和幂等源预检问题均已修复；最终代码复审 `P0/P1/P2` 均为 `0`。
- 未执行 iOS、真实舞蹈视频、Linux 或云环境测试，因为本任务未修改这些链路；6 分钟真实 4K/HEVC 转码耗时仍需后续性能样本验证。

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
- **功能缺口：** 完整 30fps 精度、身份不确定确认、音乐语义段落和云端 GPU 迁移仍未完成；Task 9 的 iOS/真机视觉、低置信度和离线重启检查仍待人工验收。
- **阶段变更：** 用户登录与正式云上传联调已延期；Stage 6 先解决真实 AI 成品闭环。
- **已缓解：** RTMDet-m/RTMPose-m 已在 Apple Silicon 完成 CPU 单帧真实推理；MPS 未通过整组门禁，当前稳定设备固定为 CPU，后续性能验收不能假设 GPU 加速。
- **已缓解：** Task 2 的 owner/path 隔离、路径穿越、并发发布、原子写入、重启恢复、非有限浮点数和 Job CAS 已有自动化回归保护；当前仅完成本地文件实现，尚未通过 API 暴露。
- **已缓解：** Task 3 已对 shell 注入、路径泄露、VFR 上限绕过、超大文件、错误容器、多流、截断音视频和并发发布增加自动化保护；当前只在 macOS 27/FFmpeg 8.1.2 验证，Linux 与真实 6 分钟性能尚未验证。
- **商品化法律风险：** OpenMMLab 代码与 checkpoint artifact 许可证门禁通过，但当前官方检测/姿态权重的训练数据包含 COCO、Objects365 和 Body7 来源。发布商业版本前必须完成训练数据与模型权重的专项法律复核；本地技术 Demo 通过不等于 App Store 法律批准。
- Terraform state 当前只保存在主检出目录本机；丢失会增加基础设施恢复难度，需要后续迁移到受保护的远端 state。

## 下一阶段建议

Stage 6 Task 9 自动实现和门禁已完成；下一步是用户在 Xcode/真机完成剩余人工验收，确认后再关闭 Task 9。

## 阶段验收记录

- 2026-07-16：用户回复“已合并并验收 Stage 5B”，Stage 5B 正式标记为“已完成”。
- 2026-07-16：用户逐项确认 Stage 6 产品设计；仓库书面规格仍待用户验收。
- 2026-07-16：用户回复“已合并并确认规格”，Stage 6 书面规格正式验收，进入实施计划编写。
- 2026-07-16：用户回复“已合并并确认实施计划”，Stage 6 开始执行 Task 1。
- 2026-07-16：Stage 6 Task 1 完整技术门禁通过，状态更新为“待验收”；尚未开始 Task 2。
- 2026-07-17：用户回复“已合并并验收 Task 1”；GitHub PR #8 合并提交 `750e047` 已核实，Task 1 正式标记为“已完成”，Task 2 尚未开始。
- 2026-07-17：用户确认开始 Task 2；状态更新为“进行中”，尚无 Task 2 产品代码或部署变更。
- 2026-07-17：Task 2 稳定 DTO、原子文件仓库、隔离工作区与 Job CAS 已实现；聚焦 `58` 项和后端全量 `197` 项测试通过，状态更新为“待验收”，尚未开始 Task 3。
- 2026-07-17：用户回复“已合并并验收 Task 2”；GitHub PR #10 合并提交 `ce3facd` 已核实，Task 2 正式标记为“已完成”，Task 3 尚未开始。
- 2026-07-17：GitHub PR #11 合并提交 `72da1c4` 已核实；用户确认开始 Task 3，状态更新为“进行中”，尚无 Task 3 产品代码、用户视频读取或部署变更。
- 2026-07-17：Task 3 媒体预检与原子分析代理已实现；媒体 `45` 项、Worker `71` 项和后端 `197` 项测试通过，最终审查无 P0/P1/P2，状态更新为“待验收”，尚未开始 Task 4。
- 2026-07-17：用户回复“已合并并验收 Task 3”；GitHub PR #12 合并提交 `c631210` 已核实，Task 3 正式标记为“已完成”，Task 4 尚未开始。
- 2026-07-17：GitHub PR #14 合并 Task 4 代码；真实 `82MAJOR Trophy` 门禁通过，得到 6 个候选和 6/6 完整代表图。
- 2026-07-17：GitHub PR #17 合并 Task 5 API 编排后，PR #18 误将其撤销；本恢复分支重新应用提交 `1543425` 与 `f93a372`，待恢复 PR 合并。
- 2026-07-17：恢复 PR #19 已合并到 `main`；Task 5 增加持久 Job 仓库、状态文件同步、重启恢复、目标选择幂等键和真实 API smoke。
- 2026-07-17：真实 `82MAJOR Trophy` API smoke 通过：`1 passed in 280.18s`，验证上传 -> 候选 -> 重启恢复 -> 目标选择；Task 7 目标分析仍未实现。
- 2026-07-17：用户确认开始 Task 7；范围为目标 RTMPose-m、基础节拍、动作时间轴、难度/重复解释和确定性 Analysis Package，不修改 iOS UI。
- 2026-07-17：Task 7 本地实现和门禁完成；本地 AI 测试 86 项、后端回归 202 项、真实 FastAPI smoke 1 项通过。真实 smoke 使用 32 秒舞者片段和 `LOCAL_AI_FRAME_STRIDE=30`，验证上传 -> 候选 -> 重启恢复 -> 选择舞者 -> `resultReady` -> ZIP 下载；完整 30fps 精度仍待后续验收。
- 2026-07-21：用户确认合并 PR #21；Task 7 以合并提交 `6b1a7a4531eafcdc7ec1dd357a29fd896b4c6c77` 标记为已完成，Task 8 尚未开始，等待开始确认。
- 2026-07-21：用户确认开始 Task 8；结果包解析、成员完整性/哈希校验、API 私有内容下载和本地存储接入已实现，聚焦 Swift 测试通过，练习页渲染与真实 API 联调进行中。
- 2026-07-21：用户确认 Task 8 PR #22 已合并，Stage 6 Task 8 标记为“已完成”。
- 2026-07-21：用户提出开始 Task 9；根据既有实施计划，Task 9 范围为单视频端到端验收、可重复本地 Demo、隐私/资源检查和长期文档，不扩展新 AI 功能，等待范围确认。
- 2026-07-21：用户确认开始 Task 9；状态更新为“进行中”，范围保持单视频验收、可重复本地 Demo、隐私/资源检查和长期文档。
- 2026-07-21：Task 9 实现完成；修复 MPS `nms_impl` 探测错误的 CPU 回退识别，三套自动门禁通过（本地 AI `89 passed`、后端 `207 passed, 1 skipped`、iOS 测试/构建通过），真实短片 smoke `1 passed in 31.35s`。状态更新为“待验收”，等待用户完成人工视觉与真机检查。

## 最后更新时间与对应 Git 提交

- 最后更新：2026-07-23（Asia/Tokyo，本次代码逻辑复查）。
- 已部署 Git 提交：`21161a288e73ebc40a5716b01db1d1f8210037a7`。
- Cloud Run scaling 收敛修复提交：`57a7554`，PR #2 合并提交 `636ed3d`。
- Firebase Authentication 初始化提交：`420493d`，PR #3 合并提交 `59dec60`。
- Stage 5B 真实云验证记录提交：`033db4e`，PR #4 合并提交 `d890ecf`。
- Stage 6 设计合并提交：`ff2350d`。
- Stage 6 实施计划合并提交：`b0d5794`。
- Stage 6 Task 1 实现提交：`49c3f52`，PR #8 合并提交 `750e047`。
- Stage 6 Task 2 实现提交：`a9be8f9`；安全与原子发布加固提交：`796f42e`、`31facdd`、`6a02bb2`、`fcce6b4`；PR #10 合并提交：`ce3facd`。
- Stage 6 Task 2 验收记录：`1744cbf`，PR #11 合并提交：`72da1c4`。
- Stage 6 Task 3 实现提交：`d0b487f`；安全加固提交：`089cf95`、`8ca0eec`；PR #12 合并提交：`c631210`。
- GitHub `main`：Task 9 验收记录 PR #24、项目删除 PR #25、内容路由修补 PR #26 与目标选择/错误状态修补 PR #27 均已合并；Task 9 的真机视觉和离线人工验收仍待完成。
