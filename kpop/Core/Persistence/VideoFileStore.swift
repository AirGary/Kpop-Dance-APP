import Foundation

struct VideoFileStore {
    let rootDirectory: URL

    static func applicationSupport(fileManager: FileManager = .default) throws -> VideoFileStore {
        let root = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return VideoFileStore(rootDirectory: root)
    }

    func importVideo(from sourceURL: URL, fileManager: FileManager = .default) throws -> ManagedFilePath {
        let fileExtension = sourceURL.pathExtension.isEmpty ? "mov" : sourceURL.pathExtension
        let relativePath = try ManagedFilePath(
            "ImportedVideos/\(UUID().uuidString).\(fileExtension)"
        )
        let destinationURL = try resolve(relativePath)

        try fileManager.createDirectory(
            at: destinationURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try fileManager.copyItem(at: sourceURL, to: destinationURL)
        return relativePath
    }

    func resolve(_ relativePath: ManagedFilePath) throws -> URL {
        try relativePath.resolve(inside: rootDirectory)
    }

    func delete(_ relativePath: ManagedFilePath, fileManager: FileManager = .default) throws {
        let fileURL = try resolve(relativePath)
        guard fileManager.fileExists(atPath: fileURL.path) else { return }
        try fileManager.removeItem(at: fileURL)
    }
}
