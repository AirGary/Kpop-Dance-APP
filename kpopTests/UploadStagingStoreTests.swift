import Foundation
import Testing
@testable import kpop

struct UploadStagingStoreTests {
    @Test
    func managedPathHashChunksAndDelete() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("UploadStagingTests-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let projectID = UUID(uuidString: "123E4567-E89B-12D3-A456-426614174000")!
        let store = UploadStagingStore(rootDirectory: root)

        let fileURL = try store.prepareFileURL(projectID: projectID)
        try Data("abcdef".utf8).write(to: fileURL)

        #expect(fileURL.path == root.appendingPathComponent(
            "UploadStaging/\(projectID.uuidString.lowercased()).mp4"
        ).path)
        #expect(store.exists(projectID: projectID))
        #expect(try store.byteCount(projectID: projectID) == 6)
        #expect(try store.sha256(projectID: projectID) == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721")
        #expect(try store.readChunk(projectID: projectID, offset: 2, count: 3) == Data("cde".utf8))

        try store.delete(projectID: projectID)
        #expect(!store.exists(projectID: projectID))
    }

    @Test
    func applicationSupportPathUsesUploadStagingDirectory() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("UploadStagingRoot-\(UUID().uuidString)", isDirectory: true)
        let manager = ApplicationSupportFileManager(root: root)

        let store = try UploadStagingStore.applicationSupport(fileManager: manager)

        #expect(store.rootDirectory == root)
    }
}

private final class ApplicationSupportFileManager: FileManager, @unchecked Sendable {
    let root: URL

    init(root: URL) {
        self.root = root
        super.init()
    }

    override func url(
        for directory: SearchPathDirectory,
        in domain: SearchPathDomainMask,
        appropriateFor url: URL?,
        create shouldCreate: Bool
    ) throws -> URL {
        root
    }
}
