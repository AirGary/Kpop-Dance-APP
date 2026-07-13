# Stage Lab Stage 2 本地最小后端设计规格

**状态：** 已确认

**日期：** 2026-07-13

**目标：** 在不创建 Google Cloud 资源、不绑定结算账户和不产生云费用的前提下，建立可本地运行、可自动测试、以后能替换为 Google Cloud 实现的 FastAPI 后端基础。

## 1. 范围

Stage 2 只完成后端合同与基础设施骨架：

- FastAPI 应用和版本化 `/v1` 路由。
- 开发认证、任务仓库和对象存储协议。
- 内存任务仓库与本地临时对象存储实现。
- 健康、认证、任务创建、读取和删除接口。
- 用户资源隔离、幂等创建、统一错误格式和隐私日志。
- OpenAPI 与固定 JSON 契约 fixture。
- Google Cloud dev Terraform 声明骨架，但不执行部署。
- 后端测试命令和初学者运行说明。

Stage 2 明确不包含：

- Google Cloud 项目创建、登录、结算或真实资源部署。
- Firebase iOS SDK、Sign in with Apple 或 iOS 网络接入。
- 签名上传 URL、断点续传或后台上传。
- Firestore、Cloud Storage、Cloud Run 的真实连接。
- 视频转码、人物检测、GPU 分析或结果包生成。
- 舞者候选、目标选择、推送通知、额度和收费。

这些能力分别进入 Stage 3 及之后的独立设计与实现周期。

## 2. 方案选择

采用端口适配器架构：Route 只处理 HTTP，Service 只处理业务规则，Repository 和 Object Store 通过协议隔离具体技术。

未采用 Firebase Emulator 优先方案，因为当前电脑没有 gcloud 和 Docker，直接引入 Java、Node 与 Firebase CLI 会增加环境复杂度。未采用单文件 FastAPI Demo，因为后续替换 Firestore 和 Cloud Storage 时会造成重复开发。

## 3. 后端目录

```text
backend/
  pyproject.toml
  README.md
  api/
    app/
      main.py
      container.py
      config.py
      middleware/
        request_context.py
      routes/
        health.py
        identity.py
        jobs.py
      schemas/
        errors.py
        identity.py
        jobs.py
      services/
        job_service.py
      ports/
        auth.py
        job_repository.py
        object_store.py
      adapters/
        auth/
          development_auth.py
        repositories/
          in_memory_job_repository.py
        storage/
          local_object_store.py
  contracts/
    fixtures/
      identity.json
      job.json
      error.json
  tests/
    unit/
    api/
    contracts/
infra/
  terraform/
    modules/
      api/
      data/
      storage/
    environments/
      dev/
```

每个 Python 文件只承担一个主要职责。Route 不直接操作字典、文件系统或未来的 Google SDK。

## 4. 组件职责

### 4.1 FastAPI App

- **输入：** HTTP 请求。
- **输出：** JSON 响应和 OpenAPI schema。
- **存储：** 不直接存储数据。
- **失败负责人：** 全局异常处理器将内部错误映射为稳定 API 错误。

`main.py` 只创建 App、注册中间件、异常处理器和路由。依赖由 `AppContainer` 提供。

### 4.2 AuthVerifier

接口接收 Bearer Token，返回不可变的 `AuthenticatedUser(user_id: str)`。

开发适配器只接受以下形式：

```text
Authorization: Bearer dev-user-a
```

Token 中的完整字符串只用于测试进程内认证，不写日志。缺失或格式无效返回 `401 unauthorized`。未来 Firebase 适配器保持相同接口，通过 Firebase Admin SDK 验证 ID Token。

### 4.3 JobRepository

接口提供：

- `create(job, idempotency_key)`
- `get_for_owner(job_id, owner_id)`
- `delete_for_owner(job_id, owner_id)`
- `find_by_idempotency_key(owner_id, idempotency_key)`

内存实现使用异步锁保护字典。同一个用户和同一个幂等键只能得到一个任务；不同用户可以使用相同幂等键。所有权检查必须在 Repository 边界执行，避免 Service 误取其他用户数据。

### 4.4 ObjectStore

接口提供按 `owner_id/job_id` 删除任务对象的方法。本地适配器只允许路径位于注入的根目录内，并拒绝绝对路径、空组件、`.` 和 `..`。

Stage 2 不提供上传接口。删除任务时调用 Object Store 清理对应本地目录，为 Stage 3 的 Cloud Storage 删除语义固定合同。

### 4.5 JobService

JobService 负责：

- 输入规格校验。
- 创建 `draft` 任务。
- 用户与幂等键去重。
- 用户所有权读取与删除。
- 调用 Object Store 清理任务对象。

Service 不读取 HTTP Header，也不构造 FastAPI Response。

## 5. 数据模型

### 5.1 创建任务请求

```json
{
  "projectId": "5dc6cb17-9df3-4f99-9f32-dd51e69f4430",
  "sourceFingerprint": "sha256:0123456789abcdef",
  "durationSeconds": 180.5,
  "byteCount": 104857600,
  "mimeType": "video/mp4"
}
```

规则：

- `projectId` 必须是 UUID。
- `sourceFingerprint` 长度为 8–128 个字符，只允许 ASCII 字母、数字、冒号、连字符和下划线。
- `durationSeconds` 必须大于 0 且不超过 360 秒。
- `byteCount` 必须大于 0 且不超过 2 GiB。
- `mimeType` 首轮只接受 `video/mp4` 和 `video/quicktime`。

### 5.2 任务响应

```json
{
  "id": "377a305d-9e09-45ba-ad1b-bbe7c6489f3f",
  "projectId": "5dc6cb17-9df3-4f99-9f32-dd51e69f4430",
  "state": "draft",
  "progress": 0.0,
  "errorCode": null,
  "createdAt": "2026-07-13T00:00:00Z",
  "updatedAt": "2026-07-13T00:00:00Z"
}
```

服务端内部额外保存 `owner_id`、输入规格和幂等键，但响应不暴露 owner ID 和幂等键。

### 5.3 删除语义

Stage 2 的删除是同步测试语义：所有权验证成功后清理本地任务对象，再从内存 Repository 删除记录，返回 HTTP `204`。对象清理失败时保留任务记录并返回 `503 storage_unavailable`，避免出现记录已删除但文件仍残留的状态。

未来异步云删除仍保留相同外部安全语义，但可以把内部状态扩展为 `cancelling -> deleted`。

## 6. HTTP API

### `GET /healthz`

- 不需要认证。
- 返回 `200 {"status":"ok","environment":"development"}`。
- 不检查外部云资源，因为 Stage 2 没有外部连接。

### `GET /v1/me`

- 需要 Bearer Token。
- 返回 `200 {"userId":"dev-user-a"}`。

### `POST /v1/jobs`

- 需要 Bearer Token 和 `Idempotency-Key` Header。
- 首次创建返回 `201` 和 Job Response。
- 同一用户、同一幂等键、同一请求体重复调用返回 `200` 和原任务。
- 同一用户、同一幂等键、不同请求体返回 `409 idempotency_conflict`。

### `GET /v1/jobs/{job_id}`

- 需要 Bearer Token。
- 所有者读取返回 `200`。
- 任务不存在或不属于当前用户都返回 `404 job_not_found`。

### `DELETE /v1/jobs/{job_id}`

- 需要 Bearer Token。
- 所有者删除成功返回 `204`。
- 任务不存在或不属于当前用户都返回 `404 job_not_found`。
- 重复删除返回 `404`，Stage 2 不保留墓碑记录。

## 7. 请求与错误格式

每个请求由中间件生成或接受合法的 `X-Request-ID`。响应始终返回 `X-Request-ID`。

错误响应统一为：

```json
{
  "error": {
    "code": "job_not_found",
    "message": "Job was not found.",
    "requestId": "01J2EXAMPLE"
  }
}
```

稳定错误码：

| HTTP | Code | 场景 |
|---|---|---|
| 401 | `unauthorized` | Token 缺失或无效 |
| 404 | `job_not_found` | 任务不存在或不属于用户 |
| 409 | `idempotency_conflict` | 幂等键对应不同请求体 |
| 422 | `validation_error` | Header、路径或 JSON 输入不符合规格 |
| 503 | `storage_unavailable` | 对象清理失败 |
| 500 | `internal_error` | 未映射异常 |

错误消息不包含 Token、用户标题、原视频名、本地绝对路径、签名 URL 或异常堆栈。

## 8. 日志与隐私

使用 Python 标准 logging 输出结构化 JSON。允许字段：

- `request_id`
- `method`
- 路由模板，不是带真实 ID 的原始 URL
- `status_code`
- `duration_ms`
- 稳定错误码

不记录 Authorization、请求体、项目标题、视频文件名、指纹全文或未来的签名 URL。单元测试捕获日志并断言敏感值不存在。

## 9. Terraform dev 骨架

Terraform 声明未来 dev 环境需要的资源边界：

- Cloud Run API，`min_instance_count = 0`。
- Firestore Native Database，新加坡区域兼容位置。
- 私有 Cloud Storage Bucket，统一 bucket-level access。
- 原视频 1 天和结果 7 天生命周期规则。
- Artifact Registry。
- API、Detection 和 Analysis 独立服务账号。
- 最小权限 IAM 输出，不创建宽泛 Editor 角色。
- 月费用 20、35、50 美元阈值所需预算变量和监控接口占位由明确变量表达，但 Stage 2 不创建结算预算，因为没有 Billing Account。

本轮不执行 `terraform apply`。如果本机没有 Terraform，只做静态文件结构检查并明确记录“未运行 Terraform CLI 验证”。安装工具和真实部署进入单独的云环境启用步骤。

## 10. 测试

### 10.1 单元测试

- 创建请求边界：0、360、超过 360 秒。
- MIME 和文件大小边界。
- 同用户幂等重放返回原任务。
- 同幂等键不同请求返回冲突。
- 不同用户使用相同幂等键互不影响。
- 本地对象路径拒绝绝对路径和路径穿越。
- Object Store 删除失败时 Repository 记录仍存在。

### 10.2 API 测试

- `/healthz` 无认证可访问。
- `/v1/me` 的成功、缺失 Token 和非法 Token。
- 创建任务的 `201`、重复创建的 `200` 和冲突的 `409`。
- 用户 A 可以读取和删除自己的任务。
- 用户 B 读取和删除用户 A 的任务均得到同样的 `404`。
- 所有错误都包含稳定 code 和 requestId。
- 所有响应都包含 `X-Request-ID`。

### 10.3 契约测试

- Pydantic 输出与 `contracts/fixtures/*.json` 一致。
- OpenAPI 包含五个已批准接口。
- Job state 使用与 iOS `AnalysisJobState.draft` 相同的字符串。
- 日期使用 UTC RFC 3339 格式。

### 10.4 验收命令

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/python -m uvicorn api.app.main:app --host 127.0.0.1 --port 8000
```

另行运行：

```bash
./scripts/verify-ios.sh
git diff --check HEAD
```

如果 Terraform CLI 可用，运行 `terraform fmt -check -recursive infra/terraform` 和 `terraform validate`；不可用时在验收报告中明确说明缺口。

## 11. 完成门槛

- 后端可在 `127.0.0.1:8000` 启动。
- 五个 HTTP 接口行为符合本规格。
- 后端全部自动测试通过。
- 用户所有权隔离和幂等行为有回归测试。
- 日志测试证明敏感字段未输出。
- 固定契约 fixture 与 OpenAPI 测试通过。
- 现有 iOS 全量验证继续通过。
- 未连接 Google Cloud，云成本为 0。
- Terraform 未部署到任何账号。
- Git 工作区干净。

完成后，Stage 3 可以在该协议基础上增加真实 Firebase 身份、签名上传 URL、可恢复上传和 24 小时清理，而不改变已批准的任务读取与用户隔离语义。
