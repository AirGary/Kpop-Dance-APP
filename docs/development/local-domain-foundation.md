# Stage 1 本地域基础

这一步为未来接入 Google Cloud 做准备，但现在仍然是完全本地的工程。它没有发送 HTTP 请求，没有上传视频，也没有调用真实 AI。目标是先把数据、文件和服务的边界固定下来，让后续接入云端时只替换服务实现，而不是重写整个 App。

## 先理解四层

### 1. `Domain/Analysis`：业务规则

- **输入是什么：** 项目 ID、任务当前状态、目标状态、舞者候选和结果描述。
- **输出是什么：** 合法的新任务状态，或者明确的非法状态转换错误。
- **存在哪里：** 这些 Swift 类型本身不存数据，只在内存中表达业务含义。
- **失败由谁处理：** `AnalysisStateMachine` 拒绝非法转换；调用它的服务决定怎样向页面展示错误或重试。

关键类型：

- `AnalysisJobState` 列出从创建、上传、分析到完成或失败的所有状态。
- `AnalysisJobSnapshot` 是某一时刻的任务快照，包含任务 ID、项目 ID、进度和错误码。
- `AnalysisStateMachine` 是唯一允许改变任务状态的规则表。
- `DancerCandidate` 是分析阶段返回给用户选择的舞者候选。
- `AnalysisResultDescriptor` 描述已经完成的结果包，不包含结果包本身的大数据。

### 2. `Core/Persistence`：本地保存

- **输入是什么：** `DanceProject`、源视频 URL、分析结果 `Data` 或受管相对路径。
- **输出是什么：** SwiftData 中的项目、复制后的视频位置、带 SHA-256 的结果包记录。
- **存在哪里：** 项目字段进入 SwiftData；视频进入 `ImportedVideos/`；结果包进入 `AnalysisPackages/<projectID>/`。
- **失败由谁处理：** Repository 把 SwiftData 错误抛给上层；File Store 把文件或完整性错误抛给调用者，调用者决定提示、重试或保留旧结果。

关键类型：

- `ManagedFilePath` 只允许安全的相对路径，拒绝绝对路径和 `..`，避免文件逃出 App 管理目录。
- `VideoFileStore` 负责复制、定位和删除导入视频。
- `AnalysisPackageStore` 负责原子保存、读取校验和删除分析包。
- `AnalysisPackageRecord` 保存 schema 版本、相对路径、字节数和 SHA-256。
- `DanceProjectRepository` 定义项目查询和增删保存接口。
- `SwiftDataDanceProjectRepository` 是该接口目前的 SwiftData 实现。

### 3. `Core/Services`：分析入口

- **输入是什么：** 项目 ID、任务 ID和用户选中的候选舞者 ID。
- **输出是什么：** 任务快照、候选舞者数组和结果描述。
- **存在哪里：** `FakeAnalysisService` 只把任务放在 actor 的内存字典中，App 退出后会消失。
- **失败由谁处理：** Service 抛出 `unknownJob`、`candidateNotFound` 或 `resultNotReady`；未来 View Model 或页面负责转换成用户能理解的提示。

`AnalysisService` 是稳定合同。现在使用 `FakeAnalysisService`；未来的 Google Cloud 实现仍然提供相同方法，因此页面不需要知道 HTTP、Token、Cloud Storage 或 Firestore 的细节。

### 4. `Models/DanceProject`：项目索引

- **输入是什么：** 用户创建项目时的标题、视频信息和后续云分析元数据。
- **输出是什么：** 首页、分析页和练习页都能读取的项目记录。
- **存在哪里：** SwiftData 数据库。
- **失败由谁处理：** `ModelContainerFactory` 负责创建数据库容器；Repository 负责数据库操作错误；App 启动层负责容器无法创建的致命错误。

Stage 1 新增的字段都有安全默认值：

- `sourceFingerprint` 用于以后判断视频是否相同。
- `remoteJobId` 连接本地项目与云任务。
- `analysisSchemaVersion` 标记结果格式版本。
- `analysisPackageRelativePath` 指向本地结果包。
- `lastPracticedAt` 用于排序或显示最近练习时间。

## Fake 分析数据流

```text
页面或测试
  -> startDetection(projectID)
  -> FakeAnalysisService 创建 AnalysisJobSnapshot
  -> AnalysisStateMachine 推进到 awaitingTarget
  <- 返回任务快照

页面或测试
  -> candidates(jobID)
  <- 返回固定的 3 个 DancerCandidate

用户选择舞者
  -> selectTarget(jobID, candidateID)
  -> AnalysisStateMachine 依次经过 queued、analyzing、resultReady、importing、completed
  <- 返回 completed 任务快照

页面或测试
  -> result(jobID)
  <- 返回 AnalysisResultDescriptor
```

这条 Fake 链路没有文件写入。未来真实云服务返回结果后，App 才会把下载的数据交给 `AnalysisPackageStore.save`，再把返回的相对路径和 schema 版本写入 `DanceProject`。

## 以后接入云端时什么不变

- 页面继续调用 `AnalysisService`。
- 任务状态继续由 `AnalysisStateMachine` 校验。
- 项目继续通过 `DanceProjectRepository` 保存。
- 视频和结果继续只通过受管相对路径访问。

会被替换或增加的部分是：真实身份认证、HTTP API 客户端、可恢复上传、云任务状态轮询、结果下载和通知。Stage 1 的 Fake 不假装这些能力已经存在。

## 初学者阅读顺序

1. `AnalysisService.swift`：先看页面未来能请求什么。
2. `AnalysisJobState.swift`：认识任务有哪些阶段。
3. `AnalysisStateMachine.swift`：理解阶段怎样合法变化。
4. `FakeAnalysisService.swift`：看一次完整业务流程怎样组合。
5. `DanceProject.swift`：看哪些信息会长期保存。
6. `DanceProjectRepository.swift` 和 `SwiftDataDanceProjectRepository.swift`：理解接口与具体数据库实现的区别。
7. `ManagedFilePath.swift`、`VideoFileStore.swift`、`AnalysisPackageStore.swift`：最后理解大文件为什么不直接放进数据库。
