import Foundation

nonisolated enum AnalysisServiceError: Error, Equatable, Sendable {
    case unknownJob(UUID)
    case candidateNotFound(String)
    case resultNotReady(UUID)
}

nonisolated protocol AnalysisService: Sendable {
    func startDetection(projectID: UUID) async throws -> AnalysisJobSnapshot
    func candidates(jobID: UUID) async throws -> [DancerCandidate]
    func selectTarget(jobID: UUID, candidateID: String) async throws -> AnalysisJobSnapshot
    func status(jobID: UUID) async throws -> AnalysisJobSnapshot
    func result(jobID: UUID) async throws -> AnalysisResultDescriptor
}
