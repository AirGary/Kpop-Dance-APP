import Foundation
import Testing
@testable import kpop

@MainActor
struct FakeAnalysisServiceTests {
    @Test
    func startDetectionIsDeterministicForAProject() async throws {
        let service = FakeAnalysisService()
        let projectID = UUID()

        let first = try await service.startDetection(projectID: projectID)
        let second = try await service.startDetection(projectID: projectID)

        #expect(first.id == second.id)
        #expect(first.projectID == projectID)
        #expect(first.state == .awaitingTarget)
    }

    @Test
    func candidatesRemainStableAcrossRequests() async throws {
        let service = FakeAnalysisService()
        let job = try await service.startDetection(projectID: UUID())

        let first = try await service.candidates(jobID: job.id)
        let second = try await service.candidates(jobID: job.id)

        #expect(first == second)
        #expect(first.count == 3)
        #expect(Set(first.map(\.id)).count == first.count)
    }

    @Test
    func selectingTargetCompletesAnalysisAndMakesResultAvailable() async throws {
        let service = FakeAnalysisService()
        let job = try await service.startDetection(projectID: UUID())
        let candidate = try #require(await service.candidates(jobID: job.id).first)

        let completed = try await service.selectTarget(
            jobID: job.id,
            candidateID: candidate.id
        )
        let status = try await service.status(jobID: job.id)
        let result = try await service.result(jobID: job.id)

        #expect(completed.state == .completed)
        #expect(completed.progress == 1)
        #expect(status == completed)
        #expect(result.jobID == job.id)
        #expect(result.projectID == job.projectID)
        #expect(result.schemaVersion == 1)
    }

    @Test
    func unknownJobRequestsAreRejected() async {
        let service = FakeAnalysisService()
        let unknownID = UUID()

        await #expect(throws: AnalysisServiceError.unknownJob(unknownID)) {
            try await service.status(jobID: unknownID)
        }
    }

    @Test
    func resultCannotBeRequestedBeforeCompletion() async throws {
        let service = FakeAnalysisService()
        let job = try await service.startDetection(projectID: UUID())

        await #expect(throws: AnalysisServiceError.resultNotReady(job.id)) {
            try await service.result(jobID: job.id)
        }
    }
}
