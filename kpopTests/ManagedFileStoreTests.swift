import Foundation
import Testing
@testable import kpop

@MainActor
struct ManagedFileStoreTests {
    @Test
    func managedPathRejectsAbsoluteAndTraversalPaths() {
        #expect(throws: ManagedFilePathError.self) {
            try ManagedFilePath("/tmp/video.mov")
        }
        #expect(throws: ManagedFilePathError.self) {
            try ManagedFilePath("../video.mov")
        }
        #expect(throws: ManagedFilePathError.self) {
            try ManagedFilePath("ImportedVideos/../video.mov")
        }
    }

    @Test
    func videoStoreCopiesResolvesAndDeletesAFile() throws {
        let fixture = try TemporaryFileFixture()
        defer { fixture.remove() }
        let sourceURL = fixture.root.appendingPathComponent("source.mov")
        let sourceData = Data("sample-video".utf8)
        try sourceData.write(to: sourceURL)
        let store = VideoFileStore(rootDirectory: fixture.root)

        let relativePath = try store.importVideo(from: sourceURL)
        let importedURL = try store.resolve(relativePath)

        #expect(relativePath.value.hasPrefix("ImportedVideos/"))
        #expect(importedURL.path.hasPrefix(fixture.root.path))
        #expect(try Data(contentsOf: importedURL) == sourceData)

        try store.delete(relativePath)
        #expect(!FileManager.default.fileExists(atPath: importedURL.path))
    }

    @Test
    func packageStoreSavesHashLoadsReplacesAndDeletesData() throws {
        let fixture = try TemporaryFileFixture()
        defer { fixture.remove() }
        let projectID = UUID()
        let store = AnalysisPackageStore(rootDirectory: fixture.root)
        let firstData = Data("abc".utf8)

        let firstRecord = try store.save(firstData, projectID: projectID, version: 1)

        #expect(firstRecord.relativePath.value == "AnalysisPackages/\(projectID.uuidString)/result-v1.bin")
        #expect(firstRecord.schemaVersion == 1)
        #expect(firstRecord.byteCount == firstData.count)
        #expect(firstRecord.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        #expect(try store.load(firstRecord) == firstData)

        let replacementData = Data("replacement".utf8)
        let replacementRecord = try store.save(replacementData, projectID: projectID, version: 1)

        #expect(replacementRecord.relativePath == firstRecord.relativePath)
        #expect(replacementRecord.sha256 != firstRecord.sha256)
        #expect(try store.load(replacementRecord) == replacementData)

        try store.delete(replacementRecord.relativePath)
        #expect(throws: CocoaError.self) {
            try store.load(replacementRecord)
        }
    }
}

private struct TemporaryFileFixture {
    let root: URL

    init() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("StageLabTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    func remove() {
        try? FileManager.default.removeItem(at: root)
    }
}
