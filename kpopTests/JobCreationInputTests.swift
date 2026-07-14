import Foundation
import Testing
@testable import kpop

@MainActor
struct JobCreationInputTests {
    @Test(arguments: [("mp4", "video/mp4"), ("mov", "video/quicktime")])
    func validVideoCreatesStableMetadata(fileExtension: String, mimeType: String) throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExtension)
        try Data(repeating: 1, count: 1_024).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        let id = UUID(uuidString: "123E4567-E89B-12D3-A456-426614174000")!
        let project = DanceProject(
            id: id,
            title: "Test",
            sourceVideoPath: url.path,
            videoDuration: 90
        )

        let input = try JobCreationInputFactory.make(project: project)

        #expect(input.request.projectId == id)
        #expect(input.request.sourceFingerprint == "project:\(id.uuidString.lowercased())")
        #expect(input.request.byteCount == 1_024)
        #expect(input.request.mimeType == mimeType)
        #expect(input.idempotencyKey == "project-\(id.uuidString.lowercased())")
    }

    @Test
    func projectWithoutVideoIsRejected() {
        let project = DanceProject(title: "Missing", videoDuration: 90)
        #expect(throws: JobCreationInputError.missingVideo) {
            try JobCreationInputFactory.make(project: project)
        }
    }

    @Test
    func unsupportedExtensionIsRejected() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("video.avi")
        try Data([1]).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        let project = DanceProject(title: "AVI", sourceVideoPath: url.path, videoDuration: 90)

        #expect(throws: JobCreationInputError.unsupportedVideoType) {
            try JobCreationInputFactory.make(project: project)
        }
    }

    @Test(arguments: [0.0, 360.0001])
    func invalidDurationIsRejected(duration: Double) throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("video.mp4")
        try Data([1]).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        let project = DanceProject(title: "Duration", sourceVideoPath: url.path, videoDuration: duration)

        #expect(throws: JobCreationInputError.invalidDuration) {
            try JobCreationInputFactory.make(project: project)
        }
    }
}
