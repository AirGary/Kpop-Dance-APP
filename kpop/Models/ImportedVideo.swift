import Foundation
import AVFoundation
import CoreTransferable
import UniformTypeIdentifiers

struct PickedVideo: Transferable {
    let fileURL: URL
    let displayName: String

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { receivedFile in
            try makeTemporaryCopy(from: receivedFile.file)
        }
    }

    static func makeTemporaryCopy(
        from sourceURL: URL,
        temporaryDirectory: URL = FileManager.default.temporaryDirectory,
        fileManager: FileManager = .default
    ) throws -> PickedVideo {
        try fileManager.createDirectory(
            at: temporaryDirectory,
            withIntermediateDirectories: true
        )

        let fileExtension = sourceURL.pathExtension.isEmpty ? "mov" : sourceURL.pathExtension
        let destinationURL = temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExtension)
        try fileManager.copyItem(at: sourceURL, to: destinationURL)

        return PickedVideo(
            fileURL: destinationURL,
            displayName: sourceURL.deletingPathExtension().lastPathComponent
        )
    }
}

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

    func copyVideo(from sourceURL: URL, displayName: String? = nil) async throws -> ImportedVideo {
        let store = try fileStore ?? VideoFileStore.applicationSupport()
        let relativePath = try store.importVideo(from: sourceURL)
        let fileURL = try store.resolve(relativePath)

        do {
            let asset = AVURLAsset(url: fileURL)
            let duration = try await asset.load(.duration).seconds
            let name = sourceURL.deletingPathExtension().lastPathComponent

            return ImportedVideo(
                fileURL: fileURL,
                displayName: displayName ?? name,
                duration: duration.isFinite ? duration : 0
            )
        } catch {
            try? store.delete(relativePath)
            throw error
        }
    }
}
