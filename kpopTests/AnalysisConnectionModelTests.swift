import Foundation
import Testing
@testable import kpop

@MainActor
struct AnalysisConnectionModelTests {
    @Test
    func successfulCreateAndFetchPersistRemoteMetadata() async throws {
        let project = try makeProject()
        defer { try? FileManager.default.removeItem(atPath: project.sourceVideoPath!) }
        let jobID = UUID()
        let client = makeClient(jobID: jobID, projectID: project.id)
        let model = AnalysisConnectionModel()

        await model.connect(project: project, client: client)

        guard case .connected(let job) = model.state else {
            Issue.record("Expected connected state")
            return
        }
        #expect(job.id == jobID)
        #expect(project.remoteJobId == jobID.uuidString)
        #expect(project.sourceFingerprint == "project:\(project.id.uuidString.lowercased())")
    }

    @Test
    func fetchFailureLeavesProjectMetadataUntouched() async throws {
        let project = try makeProject()
        defer { try? FileManager.default.removeItem(atPath: project.sourceVideoPath!) }
        let jobID = UUID()
        let client = makeClient(jobID: jobID, projectID: project.id, fetchStatus: 503)
        let model = AnalysisConnectionModel()

        await model.connect(project: project, client: client)

        guard case .failed = model.state else {
            Issue.record("Expected failed state")
            return
        }
        #expect(project.remoteJobId == nil)
        #expect(project.sourceFingerprint.isEmpty)
    }

    private func makeProject() throws -> DanceProject {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("mp4")
        try Data([1, 2, 3]).write(to: url)
        return DanceProject(
            title: "Connection",
            sourceVideoPath: url.path,
            videoDuration: 90
        )
    }

    private func makeClient(
        jobID: UUID,
        projectID: UUID,
        fetchStatus: Int = 200
    ) -> JobsAPIClient {
        let transport = HTTPTransport { request in
            let isFetch = request.httpMethod == "GET"
            let status = isFetch ? fetchStatus : 201
            let data: Data
            if status == 200 || status == 201 {
                data = Data(#"{"id":"\#(jobID.uuidString)","projectId":"\#(projectID.uuidString)","state":"draft","progress":0,"errorCode":null,"createdAt":"2026-07-13T05:00:00Z","updatedAt":"2026-07-13T05:00:00Z"}"#.utf8)
            } else {
                data = Data(#"{"error":{"code":"storage_unavailable","message":"Temporary failure.","requestId":"test"}}"#.utf8)
            }
            return (
                data,
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: status,
                    httpVersion: nil,
                    headerFields: nil
                )!
            )
        }
        return JobsAPIClient(
            configuration: JobsAPIConfiguration(
                baseURL: URL(string: "http://127.0.0.1:8000")!,
                bearerToken: "dev-user-a"
            ),
            transport: transport
        )
    }
}
