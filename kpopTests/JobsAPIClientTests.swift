import Foundation
import Testing
@testable import kpop

struct JobsAPIClientTests {
    private let projectID = UUID(uuidString: "123E4567-E89B-12D3-A456-426614174000")!
    private let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!

    @Test
    func createSendsExactContractAndDecodesCreatedJob() async throws {
        let responseData = jobJSON()
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.absoluteString == "http://127.0.0.1:8000/v1/jobs")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
            #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "project-key")
            #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")

            let body = try #require(request.httpBody)
            let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
            #expect(json["projectId"] as? String == self.projectID.uuidString.lowercased())
            #expect(json["sourceFingerprint"] as? String == "project:source")
            #expect(json["durationSeconds"] as? Double == 90)
            #expect(json["byteCount"] as? Int == 1_024)
            #expect(json["mimeType"] as? String == "video/mp4")
            return (responseData, self.response(status: 201, request: request))
        }
        let client = JobsAPIClient(configuration: configuration(), transport: transport)

        let job = try await client.createJob(request(), idempotencyKey: "project-key")

        #expect(job.id == jobID)
        #expect(job.projectId == projectID)
        #expect(job.state == .draft)
    }

    @Test
    func fetchUsesJobPathAndAcceptsFractionalTimestamp() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "GET")
            #expect(request.url?.path == "/v1/jobs/\(self.jobID.uuidString)")
            return (self.jobJSON(fractional: true), self.response(status: 200, request: request))
        }
        let client = JobsAPIClient(configuration: configuration(), transport: transport)

        let job = try await client.job(id: jobID)

        #expect(job.id == jobID)
    }

    @Test
    func backendEnvelopeBecomesSafeTypedError() async {
        let data = Data(#"{"error":{"code":"idempotency_conflict","message":"Key conflict.","requestId":"request-test"}}"#.utf8)
        let transport = HTTPTransport { request in
            (data, self.response(status: 409, request: request))
        }
        let client = JobsAPIClient(configuration: configuration(), transport: transport)

        await #expect(throws: JobsAPIError.backend(
            status: 409,
            code: "idempotency_conflict",
            message: "Key conflict."
        )) {
            try await client.createJob(request(), idempotencyKey: "project-key")
        }
    }

    @Test
    func malformedSuccessResponseIsRejected() async {
        let transport = HTTPTransport { request in
            (Data("{}".utf8), self.response(status: 201, request: request))
        }
        let client = JobsAPIClient(configuration: configuration(), transport: transport)

        await #expect(throws: JobsAPIError.decoding) {
            try await client.createJob(request(), idempotencyKey: "project-key")
        }
    }

    private func configuration() -> JobsAPIConfiguration {
        JobsAPIConfiguration(
            baseURL: URL(string: "http://127.0.0.1:8000")!,
            bearerToken: "dev-user-a"
        )
    }

    private func request() -> CreateRemoteJobRequest {
        CreateRemoteJobRequest(
            projectId: projectID,
            sourceFingerprint: "project:source",
            durationSeconds: 90,
            byteCount: 1_024,
            mimeType: "video/mp4"
        )
    }

    private func response(status: Int, request: URLRequest) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: nil
        )!
    }

    private func jobJSON(fractional: Bool = false) -> Data {
        let timestamp = fractional ? "2026-07-13T05:00:00.123Z" : "2026-07-13T05:00:00Z"
        return Data(#"{"id":"\#(jobID.uuidString.lowercased())","projectId":"\#(projectID.uuidString.lowercased())","state":"draft","progress":0,"errorCode":null,"createdAt":"\#(timestamp)","updatedAt":"\#(timestamp)"}"#.utf8)
    }
}
