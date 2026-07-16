import Foundation

nonisolated enum UploadAPIError: Error, Equatable, Sendable {
    case invalidResponse
    case transport
    case encoding
    case decoding
    case resumableSessionTerminated
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

nonisolated enum UploadProtocolKind: String, Decodable, Equatable, Sendable {
    case stageLab = "stage-lab"
    case gcsResumable = "gcs-resumable"
}

nonisolated struct UploadSession: Decodable, Equatable, Sendable {
    let uploadID: UUID
    let uploadURL: URL
    let expiresAt: Date
    let chunkSize: Int
    let offset: Int64
    let uploadProtocol: UploadProtocolKind

    private enum CodingKeys: String, CodingKey {
        case uploadID = "uploadId"
        case uploadURL = "uploadUrl"
        case expiresAt
        case chunkSize
        case offset
        case uploadProtocol
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

    func offset(
        uploadURL: URL,
        `protocol` uploadProtocol: UploadProtocolKind,
        total: Int64
    ) async throws -> Int64 {
        var request = URLRequest(url: uploadURL)
        switch uploadProtocol {
        case .stageLab:
            request.httpMethod = "HEAD"
            let (_, response) = try await perform(request, successCodes: [204])
            return try stageLabOffset(from: response)
        case .gcsResumable:
            request.httpMethod = "PUT"
            request.httpBody = Data()
            request.setValue("bytes */\(total)", forHTTPHeaderField: "Content-Range")
            let (_, response) = try await perform(
                request,
                successCodes: [200, 201, 308],
                mapsTerminatedResumableSession: true
            )
            if response.statusCode == 200 || response.statusCode == 201 {
                return total
            }
            return try gcsOffset(from: response)
        }
    }

    func putChunk(
        uploadURL: URL,
        `protocol` uploadProtocol: UploadProtocolKind,
        data: Data,
        start: Int64,
        total: Int64,
        crc32c: String?
    ) async throws -> UploadChunkResult {
        guard !data.isEmpty else {
            throw UploadAPIError.invalidResponse
        }
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "PUT"
        request.httpBody = data
        let end = start + Int64(data.count) - 1
        request.setValue("bytes \(start)-\(end)/\(total)", forHTTPHeaderField: "Content-Range")
        if uploadProtocol == .gcsResumable, end + 1 == total {
            guard let crc32c, !crc32c.isEmpty else {
                throw UploadAPIError.invalidResponse
            }
            request.setValue("crc32c=\(crc32c)", forHTTPHeaderField: "X-Goog-Hash")
        }
        let successCodes: Set<Int> = uploadProtocol == .stageLab
            ? [201, 308]
            : [200, 201, 308]
        let (_, response) = try await perform(
            request,
            successCodes: successCodes,
            mapsTerminatedResumableSession: uploadProtocol == .gcsResumable
        )
        let isComplete = uploadProtocol == .stageLab
            ? response.statusCode == 201
            : response.statusCode == 200 || response.statusCode == 201
        return UploadChunkResult(
            offset: isComplete
                ? total
                : try uploadOffset(from: response, protocol: uploadProtocol),
            isComplete: isComplete
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

    func abandon(uploadID: UUID) async throws {
        var request = URLRequest(
            url: configuration.baseURL.appending(
                path: "v1/uploads/\(uploadID.uuidString)"
            )
        )
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        _ = try await perform(request, successCodes: [204])
    }

    private func perform(
        _ request: URLRequest,
        successCodes: Set<Int>,
        mapsTerminatedResumableSession: Bool = false
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
            if mapsTerminatedResumableSession,
               (400...499).contains(httpResponse.statusCode),
               ![408, 429].contains(httpResponse.statusCode) {
                throw UploadAPIError.resumableSessionTerminated
            }
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

    private func uploadOffset(
        from response: HTTPURLResponse,
        protocol uploadProtocol: UploadProtocolKind
    ) throws -> Int64 {
        switch uploadProtocol {
        case .stageLab:
            return try stageLabOffset(from: response)
        case .gcsResumable:
            return try gcsOffset(from: response)
        }
    }

    private func stageLabOffset(from response: HTTPURLResponse) throws -> Int64 {
        guard
            let value = response.value(forHTTPHeaderField: "Upload-Offset"),
            let offset = Int64(value),
            offset >= 0
        else {
            throw UploadAPIError.invalidResponse
        }
        return offset
    }

    private func gcsOffset(from response: HTTPURLResponse) throws -> Int64 {
        guard let value = response.value(forHTTPHeaderField: "Range") else {
            return 0
        }
        let prefix = "bytes=0-"
        guard
            value.hasPrefix(prefix),
            let lastByte = Int64(value.dropFirst(prefix.count)),
            lastByte >= 0
        else {
            throw UploadAPIError.invalidResponse
        }
        return lastByte + 1
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
