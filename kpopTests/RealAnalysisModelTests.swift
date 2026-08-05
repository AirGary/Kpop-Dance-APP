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

    @Test
    func awaitingIdentityConfirmationLoadsOnceAndDecisionResumesPolling() async throws {
        let project = DanceProject(title: "Demo", phase: .analyzing)
        project.remoteJobId = "223e4567-e89b-12d3-a456-426614174000"
        let confirmation = IdentityConfirmation(
            confirmationID: "confirm-1", previousImagePath: "analysis/one.jpg", candidateImagePath: "analysis/two.jpg",
            previousInterval: CandidateAppearanceInterval(startSeconds: 1, endSeconds: 2),
            candidateInterval: CandidateAppearanceInterval(startSeconds: 2, endSeconds: 3), candidateClusterID: "candidate-1"
        )
        let service = ScriptedAnalysisService(
            snapshots: [AnalysisJobSnapshot(projectID: project.id, state: .awaitingConfirmation, progress: 0.7), AnalysisJobSnapshot(projectID: project.id, state: .failedRecoverable, progress: 0.75)],
            confirmation: confirmation
        )
        let model = RealAnalysisModel(service: service, pollIntervalNanoseconds: 0)

        await model.start(project: project)
        #expect(model.state == .awaitingIdentityConfirmation(confirmation))
        #expect(await service.confirmationCount == 1)
        await model.confirmIdentity(.same, project: project)
        #expect(await service.decisionCount == 1)
        #expect(project.phase == .analyzing)
    }
}

private actor ScriptedAnalysisService: AnalysisService {
    let snapshots: [AnalysisJobSnapshot]
    let candidateList: [DancerCandidate]
    let resultValue: AnalysisResultDescriptor?
    let confirmationValue: IdentityConfirmation?
    private(set) var selectionCount = 0
    private(set) var confirmationCount = 0
    private(set) var decisionCount = 0
    private var index = 0

    init(snapshots: [AnalysisJobSnapshot], candidates: [DancerCandidate] = [], result: AnalysisResultDescriptor? = nil, confirmation: IdentityConfirmation? = nil) {
        self.snapshots = snapshots
        self.candidateList = candidates
        self.resultValue = result
        self.confirmationValue = confirmation
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
    func identityConfirmation(jobID: UUID) async throws -> IdentityConfirmation {
        confirmationCount += 1
        return try #require(confirmationValue)
    }
    func submitIdentityConfirmation(jobID: UUID, confirmation: IdentityConfirmation, decision: IdentityDecisionValue) async throws -> AnalysisJobSnapshot {
        decisionCount += 1
        return snapshots.last ?? AnalysisJobSnapshot(projectID: UUID(), state: .queued, progress: 0)
    }
    func result(jobID: UUID) async throws -> AnalysisResultDescriptor {
        try #require(resultValue)
    }
}
