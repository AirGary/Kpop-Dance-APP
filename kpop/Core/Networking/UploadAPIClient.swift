import Foundation

nonisolated enum UploadAPIError: Error, Equatable, Sendable {
    case invalidResponse
    case transport
    case encoding
    case decoding
    case backend(status: Int, code: String, message: String)
}

nonisolated struct UploadCreateInput: Encodable, Equatable, Sendable {
    let projectID: UUID
    let sourceFingerprint: String
    let durationSeconds: Double
    let byteCount: Int64
    let mimeType: String
    let sha256: String

    private enum CodingKeys: String, CodingKey {
        case projectID = "projectId"
        case sourceFingerprint
        case durationSeconds
        case byteCount
        case mimeType
        case sha256
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(projectID.uuidString.lowercased(), forKey: .projectID)
        try container.encode(sourceFingerprint, forKey: .sourceFingerprint)
        try container.encode(durationSeconds, forKey: .durationSeconds)
        try container.encode(byteCount, forKey: .byteCount)
        try container.encode(mimeType, forKey: .mimeType)
        try container.encode(sha256, forKey: .sha256)
    }
}

nonisolated struct UploadSession: Decodable, Equatable, Sendable {
    let uploadID: UUID
    let uploadURL: URL
    let expiresAt: Date
    let chunkSize: Int
    let offset: Int64

    private enum CodingKeys: String, CodingKey {
        case uploadID = "uploadId"
        case uploadURL = "uploadUrl"
        case expiresAt
        case chunkSize
        case offset
    }
}

nonisolated struct UploadChunkResult: Equatable, Sendable {
    let offset: Int64
    let isComplete: Bool
}

nonisolated struct UploadAPIClient: Sendable {
    let configuration: JobsAPIConfiguration
    let transport: HTTPTransport

    init(configuration: JobsAPIConfiguration, transport: HTTPTransport = .live) {
        self.configuration = configuration
        self.transport = transport
    }

    func create(
        _ input: UploadCreateInput,
        idempotencyKey: String
    ) async throws -> UploadSession {
        var request = URLRequest(url: configuration.baseURL.appending(path: "v1/uploads"))
        request.httpMethod = "POST"
        do {
            request.httpBody = try JSONEncoder().encode(input)
        } catch {
            throw UploadAPIError.encoding
        }
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        let (data, _) = try await perform(request, successCodes: [200, 201])
        do {
            return try Self.decoder.decode(UploadSession.self, from: data)
        } catch {
            throw UploadAPIError.decoding
        }
    }

    func offset(uploadURL: URL) async throws -> Int64 {
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "HEAD"
        let (_, response) = try await perform(request, successCodes: [204])
        return try uploadOffset(from: response)
    }

    func putChunk(
        uploadURL: URL,
        data: Data,
        start: Int64,
        total: Int64
    ) async throws -> UploadChunkResult {
        guard !data.isEmpty else {
            throw UploadAPIError.invalidResponse
        }
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "PUT"
        request.httpBody = data
        let end = start + Int64(data.count) - 1
        request.setValue("bytes \(start)-\(end)/\(total)", forHTTPHeaderField: "Content-Range")
        let (_, response) = try await perform(request, successCodes: [201, 308])
        return UploadChunkResult(
            offset: try uploadOffset(from: response),
            isComplete: response.statusCode == 201
        )
    }

    func complete(uploadID: UUID, idempotencyKey: String) async throws -> RemoteJob {
        var request = URLRequest(
            url: configuration.baseURL.appending(
                path: "v1/uploads/\(uploadID.uuidString)/complete"
            )
        )
        request.httpMethod = "POST"
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        let (data, _) = try await perform(request, successCodes: [200, 201])
        do {
            return try Self.decoder.decode(RemoteJob.self, from: data)
        } catch {
            throw UploadAPIError.decoding
        }
    }

    private func perform(
        _ request: URLRequest,
        successCodes: Set<Int>
    ) async throws -> (Data, HTTPURLResponse) {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await transport.send(request)
        } catch let error as UploadAPIError {
            throw error
        } catch {
            throw UploadAPIError.transport
        }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw UploadAPIError.invalidResponse
        }
        guard successCodes.contains(httpResponse.statusCode) else {
            guard let envelope = try? JSONDecoder().decode(UploadAPIErrorEnvelope.self, from: data) else {
                throw UploadAPIError.invalidResponse
            }
            throw UploadAPIError.backend(
                status: httpResponse.statusCode,
                code: envelope.error.code,
                message: envelope.error.message
            )
        }
        return (data, httpResponse)
    }

    private func uploadOffset(from response: HTTPURLResponse) throws -> Int64 {
        guard
            let value = response.value(forHTTPHeaderField: "Upload-Offset"),
            let offset = Int64(value),
            offset >= 0
        else {
            throw UploadAPIError.invalidResponse
        }
        return offset
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractional.date(from: value) {
                return date
            }
            let standard = ISO8601DateFormatter()
            standard.formatOptions = [.withInternetDateTime]
            guard let date = standard.date(from: value) else {
                throw UploadAPIError.decoding
            }
            return date
        }
        return decoder
    }
}

private nonisolated struct UploadAPIErrorEnvelope: Decodable {
    struct Detail: Decodable {
        let code: String
        let message: String
    }

    let error: Detail
}
