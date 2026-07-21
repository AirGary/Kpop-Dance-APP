import Foundation
import Testing
@testable import kpop

struct AnalysisAPIClientTests {
    private let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!

    @Test
    func dancersDecodesExactCandidateContract() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "GET")
            #expect(request.url?.path == "/v1/jobs/\(self.jobID.uuidString)/dancers")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
            return (
                Data(#"[{"candidateId":"candidate-1","representativeImagePaths":["analysis/candidates/candidate-1-1.jpg","analysis/candidates/candidate-1-2.jpg","analysis/candidates/candidate-1-3.jpg"],"appearanceIntervals":[{"startSeconds":1.25,"endSeconds":4.5}],"boxSummary":{"x":0.1,"y":0.2,"width":0.3,"height":0.6},"confidence":0.91}]"#.utf8),
                self.response(status: 200, request: request)
            )
        }
        let client = AnalysisAPIClient(configuration: configuration(), transport: transport)

        let candidates = try await client.dancers(jobID: jobID)

        #expect(candidates.count == 1)
        #expect(candidates[0].candidateId == "candidate-1")
        #expect(candidates[0].appearanceIntervals[0].startSeconds == 1.25)
        #expect(candidates[0].boxSummary.height == 0.6)
    }

    @Test
    func targetSelectionSendsCandidateAndIdempotencyKey() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.path == "/v1/jobs/\(self.jobID.uuidString)/target")
            #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "target-key")
            let body = try #require(request.httpBody)
            let object = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
            #expect(object["candidateId"] as? String == "candidate-1")
            return (Data(RemoteJobJSON.draft.utf8), self.response(status: 200, request: request))
        }
        let client = AnalysisAPIClient(configuration: configuration(), transport: transport)

        let job = try await client.selectTarget(
            jobID: jobID,
            candidateID: "candidate-1",
            idempotencyKey: "target-key"
        )

        #expect(job.id == jobID)
        #expect(job.state == .queued)
    }

    @Test
    func resultDecodesChecksumAndFractionalMetadata() async throws {
        let transport = HTTPTransport { request in
            #expect(request.url?.path == "/v1/jobs/\(self.jobID.uuidString)/result")
            return (
                Data(#"{"schemaVersion":1,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","byteCount":1234,"contentPath":"analysis/result-v1.zip"}"#.utf8),
                self.response(status: 200, request: request)
            )
        }
        let client = AnalysisAPIClient(configuration: configuration(), transport: transport)

        let result = try await client.result(jobID: jobID)

        #expect(result.schemaVersion == 1)
        #expect(result.byteCount == 1234)
        #expect(result.contentPath == "analysis/result-v1.zip")
    }

    @Test
    func downloadsPrivateResultContentWithAuthHeaders() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "GET")
            #expect(request.url?.path == "/v1/jobs/\(self.jobID.uuidString)/content/analysis/result-v1.zip")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
            return (Data([0x50, 0x4b, 0x03, 0x04]), self.response(status: 200, request: request))
        }
        let client = AnalysisAPIClient(configuration: configuration(), transport: transport)

        let data = try await client.downloadContent(jobID: jobID, relativePath: "analysis/result-v1.zip")

        #expect(data == Data([0x50, 0x4b, 0x03, 0x04]))
    }

    @Test
    func candidateImagePathCannotEscapeConfiguredOrigin() throws {
        let client = AnalysisAPIClient(configuration: configuration())

        #expect(throws: AnalysisAPIError.invalidContentPath) {
            try client.contentURL(jobID: jobID, relativePath: "../private.jpg")
        }
        #expect(throws: AnalysisAPIError.invalidContentPath) {
            try client.contentURL(jobID: jobID, relativePath: "https://example.com/private.jpg")
        }
        #expect(try client.contentURL(jobID: jobID, relativePath: "analysis/candidates/1.jpg").host == "127.0.0.1")
    }

    private func configuration() -> JobsAPIConfiguration {
        JobsAPIConfiguration(baseURL: URL(string: "http://127.0.0.1:8000")!, bearerToken: "dev-user-a")
    }

    private func response(status: Int, request: URLRequest) -> HTTPURLResponse {
        HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
    }
}

private enum RemoteJobJSON {
    static let draft = """
    {"id":"223e4567-e89b-12d3-a456-426614174000","projectId":"123e4567-e89b-12d3-a456-426614174000","state":"queued","progress":0.2,"errorCode":null,"createdAt":"2026-07-13T05:00:00Z","updatedAt":"2026-07-13T05:00:00.123Z"}
    """
}
