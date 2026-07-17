import Foundation

nonisolated enum JobsAPIError: Error, Equatable, Sendable {
    case invalidConfiguration
    case invalidResponse
    case transport
    case decoding
    case backend(status: Int, code: String, message: String)
}

nonisolated struct CreateRemoteJobRequest: Encodable, Equatable, Sendable {
    let projectId: UUID
    let sourceFingerprint: String
    let durationSeconds: Double
    let byteCount: Int64
    let mimeType: String

    private enum CodingKeys: String, CodingKey {
        case projectId
        case sourceFingerprint
        case durationSeconds
        case byteCount
        case mimeType
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(projectId.uuidString.lowercased(), forKey: .projectId)
        try container.encode(sourceFingerprint, forKey: .sourceFingerprint)
        try container.encode(durationSeconds, forKey: .durationSeconds)
        try container.encode(byteCount, forKey: .byteCount)
        try container.encode(mimeType, forKey: .mimeType)
    }
}

nonisolated struct RemoteJob: Decodable, Equatable, Sendable {
    let id: UUID
    let projectId: UUID
    let state: AnalysisJobState
    let progress: Double
    let errorCode: String?
    let createdAt: Date
    let updatedAt: Date
}

nonisolated struct JobsAPIClient: Sendable {
    let configuration: JobsAPIConfiguration
    let transport: HTTPTransport

    init(configuration: JobsAPIConfiguration, transport: HTTPTransport = .live) {
        self.configuration = configuration
        self.transport = transport
    }

    func createJob(
        _ payload: CreateRemoteJobRequest,
        idempotencyKey: String
    ) async throws -> RemoteJob {
        var request = URLRequest(url: configuration.baseURL.appending(path: "v1/jobs"))
        request.httpMethod = "POST"
        request.httpBody = try JSONEncoder().encode(payload)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        if let pairingToken = configuration.pairingToken {
            request.setValue(pairingToken, forHTTPHeaderField: "X-Stage-Lab-Pairing-Token")
        }
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        return try await perform(request, successCodes: [200, 201])
    }

    func job(id: UUID) async throws -> RemoteJob {
        var request = URLRequest(
            url: configuration.baseURL.appending(path: "v1/jobs/\(id.uuidString)")
        )
        request.httpMethod = "GET"
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        if let pairingToken = configuration.pairingToken {
            request.setValue(pairingToken, forHTTPHeaderField: "X-Stage-Lab-Pairing-Token")
        }
        return try await perform(request, successCodes: [200])
    }

    private func perform(
        _ request: URLRequest,
        successCodes: Set<Int>
    ) async throws -> RemoteJob {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await transport.send(request)
        } catch {
            throw JobsAPIError.transport
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw JobsAPIError.invalidResponse
        }
        guard successCodes.contains(httpResponse.statusCode) else {
            guard let envelope = try? JSONDecoder().decode(APIErrorEnvelope.self, from: data) else {
                throw JobsAPIError.invalidResponse
            }
            throw JobsAPIError.backend(
                status: httpResponse.statusCode,
                code: envelope.error.code,
                message: envelope.error.message
            )
        }

        do {
            return try Self.decoder.decode(RemoteJob.self, from: data)
        } catch {
            throw JobsAPIError.decoding
        }
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
                throw DecodingError.dataCorruptedError(
                    in: try decoder.singleValueContainer(),
                    debugDescription: "Invalid timestamp."
                )
            }
            return date
        }
        return decoder
    }
}

private nonisolated struct APIErrorEnvelope: Decodable {
    struct Detail: Decodable {
        let code: String
        let message: String
    }

    let error: Detail
}
