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
    case metadataMismatch
}

struct AnalysisPackageStore {
    let rootDirectory: URL

    static func applicationSupport(fileManager: FileManager = .default) throws -> AnalysisPackageStore {
        let root = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return AnalysisPackageStore(rootDirectory: root)
    }

    func save(
        _ data: Data,
        projectID: UUID,
        version: Int,
        expectedSHA256: String? = nil,
        expectedByteCount: Int? = nil,
        fileManager: FileManager = .default
    ) throws -> AnalysisPackageRecord {
        let digest = Self.sha256(of: data)
        if let expectedSHA256, expectedSHA256 != digest {
            throw AnalysisPackageStoreError.metadataMismatch
        }
        if let expectedByteCount, expectedByteCount != data.count {
            throw AnalysisPackageStoreError.metadataMismatch
        }
        let relativePath = try ManagedFilePath(
            "AnalysisPackages/\(projectID.uuidString)/result-v\(version).zip"
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
            sha256: digest,
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

    func loadPackage(
        relativePath: String,
        schemaVersion: Int,
        sha256: String,
        byteCount: Int64
    ) throws -> AnalysisPackage {
        let record = AnalysisPackageRecord(
            relativePath: try ManagedFilePath(relativePath),
            schemaVersion: schemaVersion,
            sha256: sha256,
            byteCount: Int(byteCount)
        )
        return try AnalysisPackage.decode(load(record))
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
