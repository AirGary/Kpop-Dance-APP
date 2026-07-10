import Foundation

nonisolated struct AnalysisResultDescriptor: Codable, Equatable, Sendable {
    let jobID: UUID
    let projectID: UUID
    let schemaVersion: Int
    let packageName: String
}
