import Foundation
import Testing
@testable import kpop

@MainActor
struct AnalysisStateMachineTests {
    @Test
    func happyPathReachesCompleted() throws {
        var job = AnalysisJobSnapshot(projectID: UUID())
        let path: [AnalysisJobState] = [
            .preparing, .uploading, .uploaded, .detecting, .awaitingTarget,
            .queued, .analyzing, .resultReady, .importing, .completed
        ]

        for state in path {
            try AnalysisStateMachine.transition(&job, to: state)
        }

        #expect(job.state == .completed)
    }

    @Test
    func uncertainAnalysisCanResumeAfterConfirmation() throws {
        var job = AnalysisJobSnapshot(projectID: UUID(), state: .analyzing)

        try AnalysisStateMachine.transition(&job, to: .awaitingConfirmation)
        try AnalysisStateMachine.transition(&job, to: .analyzing)

        #expect(job.state == .analyzing)
    }

    @Test
    func recoverableFailureCanReturnToItsCheckpoint() throws {
        var job = AnalysisJobSnapshot(projectID: UUID(), state: .analyzing)

        try AnalysisStateMachine.transition(&job, to: .failedRecoverable)
        try AnalysisStateMachine.transition(&job, to: .analyzing)

        #expect(job.state == .analyzing)
    }

    @Test
    func cancellationEndsInDeleted() throws {
        var job = AnalysisJobSnapshot(projectID: UUID(), state: .detecting)

        try AnalysisStateMachine.transition(&job, to: .cancelling)
        try AnalysisStateMachine.transition(&job, to: .deleted)

        #expect(job.state == .deleted)
    }

    @Test
    func invalidTransitionIsRejectedWithoutChangingState() {
        var job = AnalysisJobSnapshot(projectID: UUID())

        #expect(throws: AnalysisStateTransitionError.self) {
            try AnalysisStateMachine.transition(&job, to: .completed)
        }
        #expect(job.state == .draft)
    }
}
