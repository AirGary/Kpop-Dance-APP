import Foundation
import AVFoundation

struct ImportedVideo {
    let fileURL: URL
    let displayName: String
    let duration: Double
}

struct ImportedVideoStore {
    func copyVideo(from sourceURL: URL) async throws -> ImportedVideo {
        let directory = try storageDirectory()
        let ext = sourceURL.pathExtension.isEmpty ? "mov" : sourceURL.pathExtension
        let fileURL = directory.appendingPathComponent("\(UUID().uuidString).\(ext)")

        if FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }

        try FileManager.default.copyItem(at: sourceURL, to: fileURL)

        do {
            let asset = AVURLAsset(url: fileURL)
            let duration = try await asset.load(.duration).seconds
            let name = sourceURL.deletingPathExtension().lastPathComponent

            return ImportedVideo(
                fileURL: fileURL,
                displayName: name,
                duration: duration.isFinite ? duration : 0
            )
        } catch {
            try? FileManager.default.removeItem(at: fileURL)
            throw error
        }
    }

    private func storageDirectory() throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent("ImportedVideos", isDirectory: true)
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        return directory
    }
}
