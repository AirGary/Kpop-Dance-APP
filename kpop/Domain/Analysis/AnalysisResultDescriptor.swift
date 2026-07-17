import Foundation

nonisolated struct AnalysisResultDescriptor: Codable, Equatable, Sendable {
    let jobID: UUID
    let projectID: UUID
    let schemaVersion: Int
    let packageName: String
    let sha256: String?
    let byteCount: Int64?

    init(
        jobID: UUID,
        projectID: UUID,
        schemaVersion: Int,
        packageName: String,
        sha256: String? = nil,
        byteCount: Int64? = nil
    ) {
        self.jobID = jobID
        self.projectID = projectID
        self.schemaVersion = schemaVersion
        self.packageName = packageName
        self.sha256 = sha256
        self.byteCount = byteCount
    }
}
