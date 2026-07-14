import Foundation
import Observation

enum AnalysisConnectionState: Equatable {
    case idle
    case loading
    case connected(RemoteJob)
    case failed(String)
}

@MainActor
@Observable
final class AnalysisConnectionModel {
    private(set) var state: AnalysisConnectionState = .idle

    func connect(project: DanceProject, client: JobsAPIClient) async {
        state = .loading
        do {
            let input = try JobCreationInputFactory.make(project: project)
            let created = try await client.createJob(
                input.request,
                idempotencyKey: input.idempotencyKey
            )
            let confirmed = try await client.job(id: created.id)
            guard
                confirmed.id == created.id,
                created.projectId == project.id,
                confirmed.projectId == project.id
            else {
                state = .failed("服务端返回的项目不匹配，请重试。")
                return
            }

            project.remoteJobId = confirmed.id.uuidString
            project.sourceFingerprint = input.request.sourceFingerprint
            project.updatedAt = Date()
            state = .connected(confirmed)
        } catch let error as JobCreationInputError {
            state = .failed(Self.message(for: error))
        } catch let error as JobsAPIError {
            state = .failed(Self.message(for: error))
        } catch {
            state = .failed("无法创建分析任务，请稍后重试。")
        }
    }

    private static func message(for error: JobCreationInputError) -> String {
        switch error {
        case .missingVideo: "找不到本地视频，请重新导入。"
        case .unsupportedVideoType: "目前仅支持 MP4 或 MOV 视频。"
        case .invalidDuration: "视频时长需在 6 分钟以内。"
        case .invalidByteCount: "视频文件为空或超过 2 GiB。"
        }
    }

    private static func message(for error: JobsAPIError) -> String {
        switch error {
        case .transport: "无法连接本地后端，请先启动 FastAPI。"
        case .backend(_, _, let message): message
        case .invalidConfiguration: "本地后端地址配置无效。"
        case .invalidResponse, .decoding: "后端响应无法识别，请重试。"
        }
    }
}
