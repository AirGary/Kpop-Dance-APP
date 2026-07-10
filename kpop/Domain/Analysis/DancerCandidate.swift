import Foundation

nonisolated struct DancerCandidate: Identifiable, Codable, Equatable, Sendable {
    let id: String
    let displayName: String
    let positionLabel: String
    let confidence: Double
}
