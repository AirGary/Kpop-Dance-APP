import CryptoKit
import Foundation

nonisolated enum UploadStagingError: Error, Equatable, Sendable {
    case missingFile
    case invalidOffset
    case invalidByteCount
}

nonisolated struct UploadStagingStore: Sendable {
    let rootDirectory: URL

    static func applicationSupport(
        fileManager: FileManager = .default
    ) throws -> UploadStagingStore {
        let root = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return UploadStagingStore(rootDirectory: root)
    }

    func fileURL(projectID: UUID) -> URL {
        rootDirectory
            .appendingPathComponent("UploadStaging", isDirectory: true)
            .appendingPathComponent("\(projectID.uuidString.lowercased()).mp4")
    }

    func prepareFileURL(
        projectID: UUID,
        fileManager: FileManager = .default
    ) throws -> URL {
        let url = fileURL(projectID: projectID)
        try fileManager.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        return url
    }

    func exists(projectID: UUID, fileManager: FileManager = .default) -> Bool {
        fileManager.fileExists(atPath: fileURL(projectID: projectID).path)
    }

    func byteCount(
        projectID: UUID,
        fileManager: FileManager = .default
    ) throws -> Int64 {
        let url = fileURL(projectID: projectID)
        guard fileManager.fileExists(atPath: url.path) else {
            throw UploadStagingError.missingFile
        }
        let attributes = try fileManager.attributesOfItem(atPath: url.path)
        guard
            let size = attributes[.size] as? NSNumber,
            size.int64Value > 0,
            size.int64Value <= 2_147_483_648
        else {
            throw UploadStagingError.invalidByteCount
        }
        return size.int64Value
    }

    func sha256(projectID: UUID) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL(projectID: projectID))
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    func readChunk(projectID: UUID, offset: Int64, count: Int) throws -> Data {
        guard offset >= 0, count > 0 else {
            throw UploadStagingError.invalidOffset
        }
        let handle = try FileHandle(forReadingFrom: fileURL(projectID: projectID))
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(offset))
        return try handle.read(upToCount: count) ?? Data()
    }

    func delete(
        projectID: UUID,
        fileManager: FileManager = .default
    ) throws {
        let url = fileURL(projectID: projectID)
        guard fileManager.fileExists(atPath: url.path) else { return }
        try fileManager.removeItem(at: url)
    }
}
