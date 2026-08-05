import Foundation

nonisolated enum AnalysisServiceError: Error, Equatable, Sendable {
    case unknownJob(UUID)
    case candidateNotFound(String)
    case resultNotReady(UUID)
    case backend(String)
    case transport
    case invalidResponse
}

nonisolated struct IdentityConfirmation: Equatable, Sendable {
    let confirmationID: String
    let previousImagePath: String
    let candidateImagePath: String
    let previousInterval: CandidateAppearanceInterval
    let candidateInterval: CandidateAppearanceInterval
    let candidateClusterID: String
}

nonisolated protocol AnalysisService: Sendable {
    func startDetection(projectID: UUID) async throws -> AnalysisJobSnapshot
    func candidates(jobID: UUID) async throws -> [DancerCandidate]
    func selectTarget(jobID: UUID, candidateID: String) async throws -> AnalysisJobSnapshot
    func status(jobID: UUID) async throws -> AnalysisJobSnapshot
    func identityConfirmation(jobID: UUID) async throws -> IdentityConfirmation
    func submitIdentityConfirmation(jobID: UUID, confirmation: IdentityConfirmation, decision: IdentityDecisionValue) async throws -> AnalysisJobSnapshot
    func result(jobID: UUID) async throws -> AnalysisResultDescriptor
}
