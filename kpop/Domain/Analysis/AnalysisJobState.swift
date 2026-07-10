import Foundation

enum AnalysisJobState: String, Codable, CaseIterable, Sendable {
    case draft
    case preparing
    case uploading
    case uploaded
    case detecting
    case awaitingTarget
    case queued
    case analyzing
    case awaitingConfirmation
    case resultReady
    case importing
    case completed
    case failedRecoverable
    case failedTerminal
    case cancelling
    case deleted
}
