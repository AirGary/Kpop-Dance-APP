import Foundation

nonisolated struct CandidateAppearanceInterval: Codable, Equatable, Sendable {
    let startSeconds: Double
    let endSeconds: Double
}

nonisolated struct CandidateBoxSummary: Codable, Equatable, Sendable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

nonisolated struct DancerCandidate: Identifiable, Codable, Equatable, Sendable {
    let id: String
    let displayName: String
    let positionLabel: String
    let confidence: Double
    let representativeImagePaths: [String]
    let appearanceIntervals: [CandidateAppearanceInterval]
    let boxSummary: CandidateBoxSummary?

    init(
        id: String,
        displayName: String,
        positionLabel: String,
        confidence: Double,
        representativeImagePaths: [String] = [],
        appearanceIntervals: [CandidateAppearanceInterval] = [],
        boxSummary: CandidateBoxSummary? = nil
    ) {
        self.id = id
        self.displayName = displayName
        self.positionLabel = positionLabel
        self.confidence = confidence
        self.representativeImagePaths = representativeImagePaths
        self.appearanceIntervals = appearanceIntervals
        self.boxSummary = boxSummary
    }
}
