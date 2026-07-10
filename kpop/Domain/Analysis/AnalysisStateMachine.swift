import Foundation

nonisolated enum AnalysisStateTransitionError: Error, Equatable, Sendable {
    case invalidTransition(from: AnalysisJobState, to: AnalysisJobState)
}

nonisolated enum AnalysisStateMachine {
    private static let transitions: [AnalysisJobState: Set<AnalysisJobState>] = [
        .draft: [.preparing, .cancelling],
        .preparing: [.uploading, .failedRecoverable, .failedTerminal, .cancelling],
        .uploading: [.uploaded, .failedRecoverable, .failedTerminal, .cancelling],
        .uploaded: [.detecting, .failedRecoverable, .failedTerminal, .cancelling],
        .detecting: [.awaitingTarget, .failedRecoverable, .failedTerminal, .cancelling],
        .awaitingTarget: [.queued, .cancelling],
        .queued: [.analyzing, .failedRecoverable, .failedTerminal, .cancelling],
        .analyzing: [.awaitingConfirmation, .resultReady, .failedRecoverable, .failedTerminal, .cancelling],
        .awaitingConfirmation: [.analyzing, .cancelling],
        .resultReady: [.importing, .failedRecoverable, .cancelling],
        .importing: [.completed, .failedRecoverable, .failedTerminal, .cancelling],
        .completed: [.deleted],
        .failedRecoverable: [.preparing, .uploading, .detecting, .queued, .analyzing, .importing, .cancelling],
        .failedTerminal: [.deleted],
        .cancelling: [.deleted],
        .deleted: []
    ]

    static func canTransition(
        from currentState: AnalysisJobState,
        to nextState: AnalysisJobState
    ) -> Bool {
        transitions[currentState, default: []].contains(nextState)
    }

    static func transition(
        _ job: inout AnalysisJobSnapshot,
        to nextState: AnalysisJobState
    ) throws {
        guard canTransition(from: job.state, to: nextState) else {
            throw AnalysisStateTransitionError.invalidTransition(
                from: job.state,
                to: nextState
            )
        }

        job.state = nextState
        job.updatedAt = Date()
    }
}
