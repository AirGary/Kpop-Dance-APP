import Foundation
import AVFoundation

struct ImportedVideo {
    let fileURL: URL
    let displayName: String
    let duration: Double
}

struct ImportedVideoStore {
    private let fileStore: VideoFileStore?

    init(fileStore: VideoFileStore? = nil) {
        self.fileStore = fileStore
    }

    func copyVideo(from sourceURL: URL) async throws -> ImportedVideo {
        let store = try fileStore ?? VideoFileStore.applicationSupport()
        let relativePath = try store.importVideo(from: sourceURL)
        let fileURL = try store.resolve(relativePath)

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
            try? store.delete(relativePath)
            throw error
        }
    }
}
