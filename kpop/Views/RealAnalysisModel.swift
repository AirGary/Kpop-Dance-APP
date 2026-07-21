import Foundation
import Observation

enum RealAnalysisState: Equatable {
    case idle
    case loading
    case detecting(AnalysisJobSnapshot)
    case awaitingTarget([DancerCandidate])
    case selecting(String)
    case analyzing(AnalysisJobSnapshot)
    case resultReady(AnalysisResultDescriptor)
    case failed(String, recoverable: Bool)
}

@MainActor
@Observable
final class RealAnalysisModel {
    private let service: any AnalysisService
    private let packageDownloader: (any AnalysisPackageDownloader)?
    private let packageStore: AnalysisPackageStore?
    private let pollIntervalNanoseconds: UInt64
    private(set) var state: RealAnalysisState = .idle

    init(
        service: any AnalysisService,
        packageDownloader: (any AnalysisPackageDownloader)? = nil,
        packageStore: AnalysisPackageStore? = nil,
        pollIntervalNanoseconds: UInt64 = 500_000_000
    ) {
        self.service = service
        self.packageDownloader = packageDownloader
        self.packageStore = packageStore
        self.pollIntervalNanoseconds = pollIntervalNanoseconds
    }

    var canRetry: Bool {
        if case .failed(_, let recoverable) = state { return recoverable }
        return false
    }

    func start(project: DanceProject) async {
        guard let rawJobID = project.remoteJobId, let jobID = UUID(uuidString: rawJobID) else {
            state = .failed("尚未创建真实分析任务。", recoverable: false)
            return
        }
        state = .loading
        await poll(jobID: jobID, project: project)
    }

    func select(candidateID: String, project: DanceProject) async {
        guard
            let rawJobID = project.remoteJobId,
            let jobID = UUID(uuidString: rawJobID),
            case .awaitingTarget(let candidates) = state,
            candidates.contains(where: { $0.id == candidateID })
        else {
            state = .failed("请选择有效的候选舞者。", recoverable: false)
            return
        }

        state = .selecting(candidateID)
        do {
            _ = try await service.selectTarget(jobID: jobID, candidateID: candidateID)
            project.selectedCandidateId = candidateID
            project.phase = .analyzing
            project.updatedAt = Date()
            await poll(jobID: jobID, project: project)
        } catch is CancellationError {
            return
        } catch let error as AnalysisServiceError {
            state = .failed(Self.message(for: error), recoverable: true)
        } catch {
            state = .failed("目标舞者提交失败，请重试。", recoverable: true)
        }
    }

    private func poll(jobID: UUID, project: DanceProject) async {
        while !Task.isCancelled {
            do {
                let snapshot = try await service.status(jobID: jobID)
                switch snapshot.state {
                case .detecting, .uploaded, .preparing, .uploading:
                    state = .detecting(snapshot)
                    try await pause()
                case .awaitingTarget:
                    let candidates = try await service.candidates(jobID: jobID)
                    state = .awaitingTarget(candidates)
                    return
                case .queued, .analyzing, .awaitingConfirmation, .importing:
                    state = .analyzing(snapshot)
                    try await pause()
                case .resultReady, .completed:
                    let result = try await service.result(jobID: jobID)
                    let localRecord = try await importPackageIfConfigured(result: result, project: project)
                    project.analysisSchemaVersion = result.schemaVersion
                    project.analysisPackageRelativePath = localRecord?.relativePath.value ?? result.packageName
                    project.analysisPackageSHA256 = localRecord?.sha256 ?? result.sha256
                    project.analysisPackageByteCount = localRecord.map { Int64($0.byteCount) } ?? result.byteCount
                    project.phase = .readyToPractice
                    project.updatedAt = Date()
                    state = .resultReady(result)
                    return
                case .failedRecoverable:
                    state = .failed(snapshot.errorCode ?? "分析暂时失败", recoverable: true)
                    return
                case .failedTerminal, .cancelling, .deleted, .draft:
                    state = .failed(snapshot.errorCode ?? "分析无法继续", recoverable: false)
                    return
                }
            } catch is CancellationError {
                return
            } catch let error as AnalysisServiceError {
                state = .failed(Self.message(for: error), recoverable: true)
                return
            } catch is AnalysisPackageStoreError {
                state = .failed("分析结果校验失败，请重试。", recoverable: true)
                return
            } catch {
                state = .failed("无法保存真实分析结果，请重试。", recoverable: true)
                return
            }
        }
    }

    private func importPackageIfConfigured(
        result: AnalysisResultDescriptor,
        project: DanceProject
    ) async throws -> AnalysisPackageRecord? {
        guard let packageDownloader, let packageStore else { return nil }
        let data = try await packageDownloader.downloadPackage(result: result)
        _ = try AnalysisPackage.decode(data)
        return try packageStore.save(
            data,
            projectID: project.id,
            version: result.schemaVersion,
            expectedSHA256: result.sha256,
            expectedByteCount: result.byteCount.map(Int.init)
        )
    }

    private func pause() async throws {
        if pollIntervalNanoseconds == 0 { return }
        try await Task.sleep(nanoseconds: pollIntervalNanoseconds)
    }

    private static func message(for error: AnalysisServiceError) -> String {
        switch error {
        case .unknownJob: "找不到真实分析任务。"
        case .candidateNotFound: "候选舞者已失效，请重新检测。"
        case .resultNotReady: "分析结果尚未准备好。"
        case .backend(let code): code
        case .transport: "无法连接本地分析服务。"
        case .invalidResponse: "分析服务响应无法识别。"
        }
    }
}
