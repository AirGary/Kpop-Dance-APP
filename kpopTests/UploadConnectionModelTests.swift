import Foundation
import Testing
@testable import kpop

@MainActor
struct UploadConnectionModelTests {
    private let uploadID = UUID(uuidString: "323E4567-E89B-12D3-A456-426614174000")!
    private let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!
    private let expiry = ISO8601DateFormatter().date(from: "2026-07-14T05:00:00Z")!

    @Test
    func successPersistsJobAndClearsResumeMetadata() async throws {
        let fixture = try ProjectFixture()
        defer { fixture.remove() }
        let runner = UploadRunner { request, allowsCellular, progress in
            #expect(request.projectID == fixture.project.id)
            #expect(request.sourceURL.path == fixture.videoURL.path)
            #expect(allowsCellular == false)
            await progress(.compressing)
            await progress(.hashing)
            await progress(.uploading(
                uploadID: self.uploadID,
                confirmedBytes: 3,
                totalBytes: 6,
                expiresAt: self.expiry
            ))
            await progress(.validating)
            return UploadCompletion(uploadID: self.uploadID, jobID: self.jobID)
        }
        let model = UploadConnectionModel()

        await model.start(project: fixture.project, runner: runner, allowsCellular: false)

        #expect(model.state == .completed(jobID: jobID))
        #expect(fixture.project.remoteJobId == jobID.uuidString)
        #expect(fixture.project.remoteUploadId == nil)
        #expect(fixture.project.confirmedUploadOffset == nil)
        #expect(fixture.project.uploadExpiresAt == nil)
    }

    @Test
    func failurePreservesLatestResumeMetadata() async throws {
        let fixture = try ProjectFixture()
        defer { fixture.remove() }
        let runner = UploadRunner { _, _, progress in
            await progress(.uploading(
                uploadID: self.uploadID,
                confirmedBytes: 3,
                totalBytes: 6,
                expiresAt: self.expiry
            ))
            throw UploadAPIError.transport
        }
        let model = UploadConnectionModel()

        await model.start(project: fixture.project, runner: runner, allowsCellular: true)

        #expect(model.state == .failed("无法连接本地后端，请确认服务已启动后继续上传。"))
        #expect(fixture.project.remoteJobId == nil)
        #expect(fixture.project.remoteUploadId == uploadID.uuidString)
        #expect(fixture.project.confirmedUploadOffset == 3)
        #expect(fixture.project.uploadExpiresAt == expiry)
    }

    @Test
    func missingSourceVideoFailsBeforeRunnerStarts() async {
        let project = DanceProject(
            title: "Missing",
            sourceVideoPath: "/missing/source.mov",
            videoDuration: 90
        )
        let calls = CallCounter()
        let runner = UploadRunner { _, _, _ in
            await calls.increment()
            return UploadCompletion(uploadID: self.uploadID, jobID: self.jobID)
        }
        let model = UploadConnectionModel()

        await model.start(project: project, runner: runner, allowsCellular: false)

        #expect(model.state == .failed("找不到本地视频，请重新导入。"))
        #expect(await calls.value == 0)
    }
}

private struct ProjectFixture {
    let root: URL
    let videoURL: URL
    let project: DanceProject

    @MainActor
    init() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("UploadModelTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        videoURL = root.appendingPathComponent("source.mov")
        try Data("source".utf8).write(to: videoURL)
        project = DanceProject(
            title: "Test",
            sourceVideoPath: videoURL.path,
            videoDuration: 90
        )
    }

    func remove() {
        try? FileManager.default.removeItem(at: root)
    }
}

private actor CallCounter {
    private(set) var value = 0

    func increment() {
        value += 1
    }
}
