import Foundation
import Testing
@testable import kpop

struct ResumableUploadCoordinatorTests {
    private let projectID = UUID(uuidString: "123E4567-E89B-12D3-A456-426614174000")!
    private let uploadID = UUID(uuidString: "323E4567-E89B-12D3-A456-426614174000")!
    private let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!

    @Test
    func resumesFromServerOffsetAndDeletesStagingAfterSuccess() async throws {
        let fixture = try Fixture(projectID: projectID, stagingContent: Data("abcdef".utf8))
        defer { fixture.remove() }
        let recorder = RequestSequence(
            uploadID: uploadID,
            jobID: jobID,
            projectID: projectID,
            serverOffset: 3
        )
        let progress = ProgressRecorder()
        let coordinator = ResumableUploadCoordinator(
            apiProvider: { _ in
                UploadAPIClient(
                    configuration: Self.configuration,
                    transport: HTTPTransport { request in try await recorder.send(request) }
                )
            },
            compressor: VideoCompressionService { _, _ in
                Issue.record("Existing staging file should skip compression.")
            },
            staging: fixture.store
        )

        let completion = try await coordinator.run(
            projectID: projectID,
            sourceFingerprint: "project:\(projectID.uuidString.lowercased())",
            durationSeconds: 90,
            sourceURL: fixture.sourceURL,
            allowsCellular: false,
            onProgress: { value in await progress.append(value) }
        )

        #expect(completion.uploadID == uploadID)
        #expect(completion.jobID == jobID)
        #expect(await recorder.uploadedRanges == ["bytes 3-5/6"])
        #expect(await recorder.createKeys == ["upload-\(projectID.uuidString.lowercased())"])
        #expect(await progress.values.contains(.uploading(
            uploadID: uploadID,
            confirmedBytes: 3,
            totalBytes: 6,
            expiresAt: RequestSequence.expiry
        )))
        #expect(!fixture.store.exists(projectID: projectID))
    }

    @Test
    func missingStagingFileCompressesOnceAndUploadsFiveMiBChunks() async throws {
        let fixture = try Fixture(projectID: projectID)
        defer { fixture.remove() }
        let content = Data(repeating: 7, count: 5_242_881)
        let recorder = RequestSequence(
            uploadID: uploadID,
            jobID: jobID,
            projectID: projectID,
            serverOffset: 0
        )
        let compression = CompressionRecorder(content: content)
        let coordinator = ResumableUploadCoordinator(
            apiProvider: { _ in
                UploadAPIClient(
                    configuration: Self.configuration,
                    transport: HTTPTransport { request in try await recorder.send(request) }
                )
            },
            compressor: VideoCompressionService { source, destination in
                try await compression.compress(source: source, destination: destination)
            },
            staging: fixture.store
        )

        _ = try await coordinator.run(
            projectID: projectID,
            sourceFingerprint: "project:\(projectID.uuidString.lowercased())",
            durationSeconds: 90,
            sourceURL: fixture.sourceURL,
            allowsCellular: false,
            onProgress: { _ in }
        )

        #expect(await compression.callCount == 1)
        #expect(await recorder.uploadedBodySizes == [5_242_880, 1])
    }

    @Test
    func recoverableFailurePreservesStagingFile() async throws {
        let fixture = try Fixture(projectID: projectID, stagingContent: Data("abcdef".utf8))
        defer { fixture.remove() }
        let coordinator = ResumableUploadCoordinator(
            apiProvider: { _ in
                UploadAPIClient(
                    configuration: Self.configuration,
                    transport: HTTPTransport { _ in throw URLError(.notConnectedToInternet) }
                )
            },
            compressor: VideoCompressionService { _, _ in },
            staging: fixture.store
        )

        await #expect(throws: UploadAPIError.transport) {
            try await coordinator.run(
                projectID: projectID,
                sourceFingerprint: "project:\(projectID.uuidString.lowercased())",
                durationSeconds: 90,
                sourceURL: fixture.sourceURL,
                allowsCellular: false,
                onProgress: { _ in }
            )
        }

        #expect(fixture.store.exists(projectID: projectID))
    }

    private static let configuration = JobsAPIConfiguration(
        baseURL: URL(string: "http://127.0.0.1:8000")!,
        bearerToken: "dev-user-a"
    )
}

private struct Fixture {
    let root: URL
    let store: UploadStagingStore
    let sourceURL: URL

    init(projectID: UUID, stagingContent: Data? = nil) throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("CoordinatorTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        store = UploadStagingStore(rootDirectory: root)
        sourceURL = root.appendingPathComponent("source.mov")
        try Data("source".utf8).write(to: sourceURL)
        if let stagingContent {
            try stagingContent.write(to: store.prepareFileURL(projectID: projectID))
        }
    }

    func remove() {
        try? FileManager.default.removeItem(at: root)
    }
}

private actor CompressionRecorder {
    let content: Data
    private(set) var callCount = 0

    init(content: Data) {
        self.content = content
    }

    func compress(source: URL, destination: URL) throws {
        callCount += 1
        try content.write(to: destination)
    }
}

private actor ProgressRecorder {
    private(set) var values: [UploadProgress] = []

    func append(_ value: UploadProgress) {
        values.append(value)
    }
}

private actor RequestSequence {
    static let expiry = ISO8601DateFormatter().date(from: "2026-07-14T05:00:00Z")!

    let uploadID: UUID
    let jobID: UUID
    let projectID: UUID
    let serverOffset: Int64
    private(set) var uploadedRanges: [String] = []
    private(set) var uploadedBodySizes: [Int] = []
    private(set) var createKeys: [String] = []
    private var currentOffset: Int64

    init(uploadID: UUID, jobID: UUID, projectID: UUID, serverOffset: Int64) {
        self.uploadID = uploadID
        self.jobID = jobID
        self.projectID = projectID
        self.serverOffset = serverOffset
        currentOffset = serverOffset
    }

    func send(_ request: URLRequest) throws -> (Data, URLResponse) {
        if request.httpMethod == "POST", request.url?.path == "/v1/uploads" {
            createKeys.append(request.value(forHTTPHeaderField: "Idempotency-Key") ?? "")
            let body = Data(#"{"uploadId":"\#(uploadID.uuidString.lowercased())","uploadUrl":"http://127.0.0.1:8000/upload?token=opaque","expiresAt":"2026-07-14T05:00:00Z","chunkSize":5242880,"offset":0,"uploadProtocol":"stage-lab"}"#.utf8)
            return (body, response(status: 201, request: request))
        }
        if request.httpMethod == "HEAD" {
            return (
                Data(),
                response(status: 204, request: request, headers: ["Upload-Offset": "\(serverOffset)"])
            )
        }
        if request.httpMethod == "PUT" {
            let body = request.httpBody ?? Data()
            uploadedBodySizes.append(body.count)
            uploadedRanges.append(request.value(forHTTPHeaderField: "Content-Range") ?? "")
            currentOffset += Int64(body.count)
            let total = Int64(request.value(forHTTPHeaderField: "Content-Range")?.split(separator: "/").last ?? "0") ?? 0
            return (
                Data(),
                response(
                    status: currentOffset == total ? 201 : 308,
                    request: request,
                    headers: ["Upload-Offset": "\(currentOffset)"]
                )
            )
        }
        let body = Data(#"{"id":"\#(jobID.uuidString.lowercased())","projectId":"\#(projectID.uuidString.lowercased())","state":"draft","progress":0,"errorCode":null,"createdAt":"2026-07-13T05:00:00Z","updatedAt":"2026-07-13T05:00:00Z"}"#.utf8)
        return (body, response(status: 201, request: request))
    }

    private func response(
        status: Int,
        request: URLRequest,
        headers: [String: String]? = nil
    ) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: headers
        )!
    }
}
