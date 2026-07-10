import Foundation

enum ManagedFilePathError: Error, Equatable {
    case empty
    case absolutePath
    case invalidComponent(String)
    case outsideRoot
}

struct ManagedFilePath: Codable, Equatable, Hashable, Sendable {
    let value: String

    init(_ value: String) throws {
        guard !value.isEmpty else {
            throw ManagedFilePathError.empty
        }
        guard !(value as NSString).isAbsolutePath else {
            throw ManagedFilePathError.absolutePath
        }

        let components = value.split(separator: "/", omittingEmptySubsequences: false)
        if let invalid = components.first(where: { $0.isEmpty || $0 == "." || $0 == ".." }) {
            throw ManagedFilePathError.invalidComponent(String(invalid))
        }

        self.value = value
    }

    func resolve(inside rootDirectory: URL) throws -> URL {
        let root = rootDirectory.standardizedFileURL
        let resolved = root.appendingPathComponent(value).standardizedFileURL
        let rootPrefix = root.path.hasSuffix("/") ? root.path : root.path + "/"

        guard resolved.path.hasPrefix(rootPrefix) else {
            throw ManagedFilePathError.outsideRoot
        }
        return resolved
    }
}
