import Foundation
import Testing
@testable import kpop

struct UploadAPIClientTests {
    private let projectID = UUID(uuidString: "123E4567-E89B-12D3-A456-426614174000")!
    private let uploadID = UUID(uuidString: "323E4567-E89B-12D3-A456-426614174000")!
    private let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!

    @Test
    func createUsesExactContractAndDecodesSession() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.absoluteString == "http://127.0.0.1:8000/v1/uploads")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
            #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "create-key")
            #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
            let body = try #require(request.httpBody)
            let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
            #expect(json["projectId"] as? String == self.projectID.uuidString.lowercased())
            #expect(json["sourceFingerprint"] as? String == "sha256:source")
            #expect(json["durationSeconds"] as? Double == 90)
            #expect(json["byteCount"] as? Int == 6)
            #expect(json["mimeType"] as? String == "video/mp4")
            #expect(json["sha256"] as? String == String(repeating: "a", count: 64))
            return (self.sessionJSON(), self.response(status: 201, request: request))
        }
        let client = UploadAPIClient(configuration: configuration(), transport: transport)

        let session = try await client.create(input(), idempotencyKey: "create-key")

        #expect(session.uploadID == uploadID)
        #expect(session.chunkSize == 5_242_880)
        #expect(session.offset == 0)
        #expect(session.uploadURL.query == "token=opaque")
    }

    @Test
    func offsetUsesSignedURLVerbatimWithoutBearer() async throws {
        let signedURL = URL(string: "http://127.0.0.1:8000/v1/uploads/\(uploadID)/content?token=secret")!
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "HEAD")
            #expect(request.url == signedURL)
            #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
            return (
                Data(),
                self.response(
                    status: 204,
                    request: request,
                    headers: ["Upload-Offset": "3", "Upload-Length": "6"]
                )
            )
        }
        let client = UploadAPIClient(configuration: configuration(), transport: transport)

        let offset = try await client.offset(uploadURL: signedURL)

        #expect(offset == 3)
    }

    @Test
    func putChunkSetsExactRangeAndAcceptsResumeStatus() async throws {
        let signedURL = URL(string: "http://127.0.0.1:8000/upload?token=secret")!
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "PUT")
            #expect(request.url == signedURL)
            #expect(request.httpBody == Data("abc".utf8))
            #expect(request.value(forHTTPHeaderField: "Content-Range") == "bytes 3-5/6")
            #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
            return (
                Data(),
                self.response(status: 308, request: request, headers: ["Upload-Offset": "6"])
            )
        }
        let client = UploadAPIClient(configuration: configuration(), transport: transport)

        let result = try await client.putChunk(
            uploadURL: signedURL,
            data: Data("abc".utf8),
            start: 3,
            total: 6
        )

        #expect(result.offset == 6)
        #expect(result.isComplete == false)
    }

    @Test
    func completeUsesBearerAndDecodesJob() async throws {
        let transport = HTTPTransport { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.path == "/v1/uploads/\(self.uploadID.uuidString)/complete")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
            #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "complete-key")
            return (self.jobJSON(), self.response(status: 201, request: request))
        }
        let client = UploadAPIClient(configuration: configuration(), transport: transport)

        let job = try await client.complete(uploadID: uploadID, idempotencyKey: "complete-key")

        #expect(job.id == jobID)
        #expect(job.state == .draft)
    }

    @Test
    func backendEnvelopeBecomesSafeTypedError() async {
        let data = Data(#"{"error":{"code":"upload_incomplete","message":"Upload is incomplete.","requestId":"request-test"}}"#.utf8)
        let transport = HTTPTransport { request in
            (data, self.response(status: 409, request: request))
        }
        let client = UploadAPIClient(configuration: configuration(), transport: transport)

        await #expect(throws: UploadAPIError.backend(
            status: 409,
            code: "upload_incomplete",
            message: "Upload is incomplete."
        )) {
            try await client.complete(uploadID: uploadID, idempotencyKey: "complete-key")
        }
    }

    private func configuration() -> JobsAPIConfiguration {
        JobsAPIConfiguration(
            baseURL: URL(string: "http://127.0.0.1:8000")!,
            bearerToken: "dev-user-a"
        )
    }

    private func input() -> UploadCreateInput {
        UploadCreateInput(
            projectID: projectID,
            sourceFingerprint: "sha256:source",
            durationSeconds: 90,
            byteCount: 6,
            mimeType: "video/mp4",
            sha256: String(repeating: "a", count: 64)
        )
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

    private func sessionJSON() -> Data {
        Data(#"{"uploadId":"\#(uploadID.uuidString.lowercased())","uploadUrl":"http://127.0.0.1:8000/v1/uploads/\#(uploadID.uuidString.lowercased())/content?token=opaque","expiresAt":"2026-07-14T05:00:00Z","chunkSize":5242880,"offset":0}"#.utf8)
    }

    private func jobJSON() -> Data {
        Data(#"{"id":"\#(jobID.uuidString.lowercased())","projectId":"\#(projectID.uuidString.lowercased())","state":"draft","progress":0,"errorCode":null,"createdAt":"2026-07-13T05:00:00Z","updatedAt":"2026-07-13T05:00:00Z"}"#.utf8)
    }
}
