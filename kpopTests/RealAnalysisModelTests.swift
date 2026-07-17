import Foundation
import Testing
@testable import kpop

@MainActor
struct RealAnalysisModelTests {
    @Test
    func pollingStopsAtAwaitingTargetAndLoadsCandidates() async throws {
        let project = DanceProject(title: "Demo", phase: .analyzing)
        project.remoteJobId = "223e4567-e89b-12d3-a456-426614174000"
        let service = ScriptedAnalysisService(
            snapshots: [
                AnalysisJobSnapshot(projectID: project.id, state: .detecting, progress: 0.4),
                AnalysisJobSnapshot(projectID: project.id, state: .awaitingTarget, progress: 0.6)
            ],
            candidates: [DancerCandidate(id: "candidate-1", displayName: "舞者 1", positionLabel: "中部", confidence: 0.9)]
        )
        let model = RealAnalysisModel(service: service, pollIntervalNanoseconds: 0)

        await model.start(project: project)

        #expect(model.state == .awaitingTarget([
            DancerCandidate(id: "candidate-1", displayName: "舞者 1", positionLabel: "中部", confidence: 0.9)
        ]))
    }

    @Test
    func selectingCandidateUsesOneStableSelectionAndReachesResult() async throws {
        let project = DanceProject(title: "Demo", phase: .needsDancerSelection)
        project.remoteJobId = "223e4567-e89b-12d3-a456-426614174000"
        let result = AnalysisResultDescriptor(
            jobID: UUID(uuidString: project.remoteJobId!)!,
            projectID: project.id,
            schemaVersion: 1,
            packageName: "analysis/result-v1.zip",
            sha256: String(repeating: "a", count: 64),
            byteCount: 100
        )
        let service = ScriptedAnalysisService(
            snapshots: [AnalysisJobSnapshot(projectID: project.id, state: .awaitingTarget, progress: 0.6), AnalysisJobSnapshot(projectID: project.id, state: .resultReady, progress: 1)],
            candidates: [DancerCandidate(id: "candidate-1", displayName: "舞者 1", positionLabel: "中部", confidence: 0.9)],
            result: result
        )
        let model = RealAnalysisModel(service: service, pollIntervalNanoseconds: 0)

        await model.start(project: project)
        await model.select(candidateID: "candidate-1", project: project)

        #expect(await service.selectionCount == 1)
        #expect(model.state == .resultReady(result))
        #expect(project.selectedCandidateId == "candidate-1")
        #expect(project.analysisPackageSHA256 == String(repeating: "a", count: 64))
    }

    @Test
    func recoverableFailureIsRetryableWithoutManualStateSkip() async throws {
        let project = DanceProject(title: "Demo")
        project.remoteJobId = UUID().uuidString
        let service = ScriptedAnalysisService(
            snapshots: [AnalysisJobSnapshot(projectID: project.id, state: .failedRecoverable, progress: 0.3, errorCode: "worker_unavailable")]
        )
        let model = RealAnalysisModel(service: service, pollIntervalNanoseconds: 0)

        await model.start(project: project)

        #expect(model.state == .failed("worker_unavailable", recoverable: true))
        #expect(model.canRetry)
    }
}

private actor ScriptedAnalysisService: AnalysisService {
    let snapshots: [AnalysisJobSnapshot]
    let candidateList: [DancerCandidate]
    let resultValue: AnalysisResultDescriptor?
    private(set) var selectionCount = 0
    private var index = 0

    init(snapshots: [AnalysisJobSnapshot], candidates: [DancerCandidate] = [], result: AnalysisResultDescriptor? = nil) {
        self.snapshots = snapshots
        self.candidateList = candidates
        self.resultValue = result
    }

    func startDetection(projectID: UUID) async throws -> AnalysisJobSnapshot { try await status(jobID: UUID()) }
    func candidates(jobID: UUID) async throws -> [DancerCandidate] { candidateList }
    func selectTarget(jobID: UUID, candidateID: String) async throws -> AnalysisJobSnapshot {
        selectionCount += 1
        return snapshots.last ?? AnalysisJobSnapshot(projectID: UUID(), state: .resultReady, progress: 1)
    }
    func status(jobID: UUID) async throws -> AnalysisJobSnapshot {
        let snapshot = snapshots[min(index, snapshots.count - 1)]
        index += 1
        return snapshot
    }
    func result(jobID: UUID) async throws -> AnalysisResultDescriptor {
        try #require(resultValue)
    }
}
