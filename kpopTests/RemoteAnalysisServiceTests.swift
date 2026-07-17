import Foundation
import Testing
@testable import kpop

struct RemoteAnalysisServiceTests {
    @Test
    func mapsServerCandidatesToDomainCandidates() async throws {
        let client = AnalysisAPIClient(configuration: configuration()) { request in
            let data = Data(#"[{"candidateId":"candidate-7","representativeImagePaths":["analysis/a.jpg","analysis/b.jpg","analysis/c.jpg"],"appearanceIntervals":[{"startSeconds":0.25,"endSeconds":5.5}],"boxSummary":{"x":0.2,"y":0.1,"width":0.3,"height":0.7},"confidence":0.88}]"#.utf8)
            return (data, response(status: 200, request: request))
        }
        let service = RemoteAnalysisService(client: client)

        let candidates = try await service.candidates(jobID: UUID())

        let expected = DancerCandidate(
            id: "candidate-7",
            displayName: "舞者 1",
            positionLabel: "画面中部",
            confidence: 0.88,
            representativeImagePaths: ["analysis/a.jpg", "analysis/b.jpg", "analysis/c.jpg"]
        )
        #expect(candidates.count == 1)
        #expect(candidates[0].id == expected.id)
        #expect(candidates[0].representativeImagePaths == expected.representativeImagePaths)
        #expect(candidates[0].positionLabel == expected.positionLabel)
    }

    @Test
    func targetSelectionUsesStableIdempotencyKey() async throws {
        let keyBox = KeyBox()
        let client = AnalysisAPIClient(configuration: configuration()) { request in
            await keyBox.set(request.value(forHTTPHeaderField: "Idempotency-Key"))
            return (Data(RemoteJobJSON.queued.utf8), response(status: 200, request: request))
        }
        let service = RemoteAnalysisService(client: client)
        let jobID = UUID(uuidString: "223E4567-E89B-12D3-A456-426614174000")!

        _ = try await service.selectTarget(jobID: jobID, candidateID: "candidate-1")
        _ = try await service.selectTarget(jobID: jobID, candidateID: "candidate-1")

        #expect(await keyBox.value == "target-223e4567-e89b-12d3-a456-426614174000-candidate-1")
    }

    private func configuration() -> JobsAPIConfiguration {
        JobsAPIConfiguration(baseURL: URL(string: "http://127.0.0.1:8000")!, bearerToken: "dev-user-a")
    }

    private func response(status: Int, request: URLRequest) -> HTTPURLResponse {
        HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
    }
}

private actor KeyBox {
    private(set) var value: String?

    func set(_ value: String?) {
        self.value = value
    }
}

private enum RemoteJobJSON {
    static let queued = """
    {"id":"223e4567-e89b-12d3-a456-426614174000","projectId":"123e4567-e89b-12d3-a456-426614174000","state":"queued","progress":0.2,"errorCode":null,"createdAt":"2026-07-13T05:00:00Z","updatedAt":"2026-07-13T05:00:00.123Z"}
    """
}
