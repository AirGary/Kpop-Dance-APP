import Foundation
import Observation

nonisolated struct ProjectUploadRequest: Equatable, Sendable {
    let projectID: UUID
    let sourceFingerprint: String
    let durationSeconds: Double
    let sourceURL: URL
}

nonisolated struct UploadRunner: Sendable {
    private let operation: @Sendable (
        ProjectUploadRequest,
        Bool,
        @escaping @Sendable (UploadProgress) async -> Void
    ) async throws -> UploadCompletion

    init(
        _ operation: @escaping @Sendable (
            ProjectUploadRequest,
            Bool,
            @escaping @Sendable (UploadProgress) async -> Void
        ) async throws -> UploadCompletion
    ) {
        self.operation = operation
    }

    init(coordinator: ResumableUploadCoordinator) {
        operation = { request, allowsCellular, progress in
            try await coordinator.run(
                projectID: request.projectID,
                sourceFingerprint: request.sourceFingerprint,
                durationSeconds: request.durationSeconds,
                sourceURL: request.sourceURL,
                allowsCellular: allowsCellular,
                onProgress: progress
            )
        }
    }

    func run(
        request: ProjectUploadRequest,
        allowsCellular: Bool,
        onProgress: @escaping @Sendable (UploadProgress) async -> Void
    ) async throws -> UploadCompletion {
        try await operation(request, allowsCellular, onProgress)
    }
}

enum UploadViewState: Equatable {
    case ready
    case compressing
    case hashing
    case uploading(Double)
    case validating
    case completed(jobID: UUID)
    case failed(String)
}

@MainActor
@Observable
final class UploadConnectionModel {
    private(set) var state: UploadViewState = .ready
    private weak var activeProject: DanceProject?

    func start(
        project: DanceProject,
        runner: UploadRunner,
        allowsCellular: Bool
    ) async {
        guard
            let path = project.sourceVideoPath,
            FileManager.default.fileExists(atPath: path)
        else {
            state = .failed("找不到本地视频，请重新导入。")
            return
        }
        guard project.videoDuration > 0, project.videoDuration <= 360 else {
            state = .failed("视频时长需在 6 分钟以内。")
            return
        }

        let fingerprint = project.sourceFingerprint.isEmpty
            ? "project:\(project.id.uuidString.lowercased())"
            : project.sourceFingerprint
        let request = ProjectUploadRequest(
            projectID: project.id,
            sourceFingerprint: fingerprint,
            durationSeconds: project.videoDuration,
            sourceURL: URL(fileURLWithPath: path)
        )
        activeProject = project
        state = .compressing
        defer { activeProject = nil }

        do {
            let completion = try await runner.run(
                request: request,
                allowsCellular: allowsCellular
            ) { [weak self] progress in
                await self?.apply(progress)
            }
            project.sourceFingerprint = fingerprint
            project.remoteJobId = completion.jobID.uuidString
            project.remoteUploadId = nil
            project.confirmedUploadOffset = nil
            project.uploadExpiresAt = nil
            project.updatedAt = Date()
            state = .completed(jobID: completion.jobID)
        } catch let error as UploadAPIError {
            state = .failed(Self.message(for: error))
        } catch let error as UploadStagingError {
            state = .failed(Self.message(for: error))
        } catch {
            state = .failed("视频上传未完成，压缩副本已保留，可继续上传。")
        }
    }

    private func apply(_ progress: UploadProgress) {
        switch progress {
        case .compressing:
            state = .compressing
        case .hashing:
            state = .hashing
        case .uploading(let uploadID, let confirmedBytes, let totalBytes, let expiresAt):
            activeProject?.remoteUploadId = uploadID.uuidString
            activeProject?.confirmedUploadOffset = confirmedBytes
            activeProject?.uploadExpiresAt = expiresAt
            activeProject?.updatedAt = Date()
            let fraction = totalBytes > 0 ? Double(confirmedBytes) / Double(totalBytes) : 0
            state = .uploading(min(max(fraction, 0), 1))
        case .validating:
            state = .validating
        }
    }

    private static func message(for error: UploadAPIError) -> String {
        switch error {
        case .transport:
            "无法连接本地后端，请确认服务已启动后继续上传。"
        case .backend(_, _, let message):
            message
        case .invalidResponse, .encoding, .decoding, .resumableSessionTerminated:
            "后端响应无法识别，请继续上传。"
        }
    }

    private static func message(for error: UploadStagingError) -> String {
        switch error {
        case .missingFile:
            "压缩副本不存在，请重新开始上传。"
        case .invalidOffset, .invalidByteCount:
            "压缩副本无效，请重新开始上传。"
        }
    }
}
