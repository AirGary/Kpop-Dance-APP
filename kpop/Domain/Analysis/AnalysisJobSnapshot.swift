import Foundation

nonisolated struct AnalysisJobSnapshot: Identifiable, Codable, Equatable, Sendable {
    let id: UUID
    let projectID: UUID
    var state: AnalysisJobState
    var progress: Double
    var errorCode: String?
    var updatedAt: Date

    init(
        id: UUID = UUID(),
        projectID: UUID,
        state: AnalysisJobState = .draft,
        progress: Double = 0,
        errorCode: String? = nil,
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.projectID = projectID
        self.state = state
        self.progress = min(max(progress, 0), 1)
        self.errorCode = errorCode
        self.updatedAt = updatedAt
    }
}
