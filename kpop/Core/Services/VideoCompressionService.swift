import AVFoundation
import Foundation

nonisolated enum VideoCompressionError: Error, Equatable, Sendable {
    case exportUnavailable
}

nonisolated struct VideoCompressionService: Sendable {
    static let presetName = AVAssetExportPreset1920x1080
    static let outputFileType: AVFileType = .mp4

    private let operation: @Sendable (URL, URL) async throws -> Void

    init(_ operation: @escaping @Sendable (URL, URL) async throws -> Void) {
        self.operation = operation
    }

    func compress(sourceURL: URL, destinationURL: URL) async throws {
        try await operation(sourceURL, destinationURL)
    }

    static let live = VideoCompressionService { sourceURL, destinationURL in
        let asset = AVURLAsset(url: sourceURL)
        guard let exportSession = AVAssetExportSession(
            asset: asset,
            presetName: Self.presetName
        ) else {
            throw VideoCompressionError.exportUnavailable
        }
        try? FileManager.default.removeItem(at: destinationURL)
        try await exportSession.export(to: destinationURL, as: Self.outputFileType)
    }
}
