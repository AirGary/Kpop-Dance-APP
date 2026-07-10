import CryptoKit
import Foundation

struct AnalysisPackageRecord: Codable, Equatable, Sendable {
    let relativePath: ManagedFilePath
    let schemaVersion: Int
    let sha256: String
    let byteCount: Int
}

enum AnalysisPackageStoreError: Error, Equatable {
    case integrityMismatch
}

struct AnalysisPackageStore {
    let rootDirectory: URL

    func save(
        _ data: Data,
        projectID: UUID,
        version: Int,
        fileManager: FileManager = .default
    ) throws -> AnalysisPackageRecord {
        let relativePath = try ManagedFilePath(
            "AnalysisPackages/\(projectID.uuidString)/result-v\(version).bin"
        )
        let destinationURL = try relativePath.resolve(inside: rootDirectory)
        let directory = destinationURL.deletingLastPathComponent()
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)

        let temporaryURL = directory.appendingPathComponent(".\(UUID().uuidString).tmp")
        try data.write(to: temporaryURL, options: .atomic)

        do {
            if fileManager.fileExists(atPath: destinationURL.path) {
                _ = try fileManager.replaceItemAt(destinationURL, withItemAt: temporaryURL)
            } else {
                try fileManager.moveItem(at: temporaryURL, to: destinationURL)
            }
        } catch {
            try? fileManager.removeItem(at: temporaryURL)
            throw error
        }

        return AnalysisPackageRecord(
            relativePath: relativePath,
            schemaVersion: version,
            sha256: Self.sha256(of: data),
            byteCount: data.count
        )
    }

    func load(_ record: AnalysisPackageRecord) throws -> Data {
        let fileURL = try record.relativePath.resolve(inside: rootDirectory)
        let data = try Data(contentsOf: fileURL)
        guard data.count == record.byteCount, Self.sha256(of: data) == record.sha256 else {
            throw AnalysisPackageStoreError.integrityMismatch
        }
        return data
    }

    func delete(_ relativePath: ManagedFilePath, fileManager: FileManager = .default) throws {
        let fileURL = try relativePath.resolve(inside: rootDirectory)
        guard fileManager.fileExists(atPath: fileURL.path) else { return }
        try fileManager.removeItem(at: fileURL)
    }

    private static func sha256(of data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
