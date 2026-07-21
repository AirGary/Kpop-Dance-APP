import Foundation

nonisolated enum AnalysisAPIError: Error, Equatable, Sendable {
    case invalidContentPath
    case invalidResponse
    case transport
    case decoding
    case backend(status: Int, code: String, message: String)
}

nonisolated struct AnalysisAppearanceIntervalDTO: Decodable, Equatable, Sendable {
    let startSeconds: Double
    let endSeconds: Double
}

nonisolated struct AnalysisBoxSummaryDTO: Decodable, Equatable, Sendable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

nonisolated struct AnalysisCandidateDTO: Decodable, Equatable, Sendable {
    let candidateId: String
    let representativeImagePaths: [String]
    let appearanceIntervals: [AnalysisAppearanceIntervalDTO]
    let boxSummary: AnalysisBoxSummaryDTO
    let confidence: Double
}

nonisolated struct AnalysisResultDTO: Decodable, Equatable, Sendable {
    let schemaVersion: Int
    let sha256: String
    let byteCount: Int64
    let contentPath: String
}

nonisolated struct AnalysisAPIClient: Sendable {
    let configuration: JobsAPIConfiguration
    let transport: HTTPTransport

    init(configuration: JobsAPIConfiguration, transport: HTTPTransport = .live) {
        self.configuration = configuration
        self.transport = transport
    }

    init(
        configuration: JobsAPIConfiguration,
        send: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse)
    ) {
        self.init(configuration: configuration, transport: HTTPTransport(send: send))
    }

    func dancers(jobID: UUID) async throws -> [AnalysisCandidateDTO] {
        let request = makeRequest(path: "v1/jobs/\(jobID.uuidString)/dancers", method: "GET")
        let candidates: [AnalysisCandidateDTO] = try await perform(request, successCodes: [200])
        for candidate in candidates {
            for path in candidate.representativeImagePaths {
                _ = try contentURL(jobID: jobID, relativePath: path)
            }
        }
        return candidates
    }

    func selectTarget(
        jobID: UUID,
        candidateID: String,
        idempotencyKey: String
    ) async throws -> RemoteJob {
        var request = makeRequest(path: "v1/jobs/\(jobID.uuidString)/target", method: "POST")
        request.httpBody = try JSONEncoder().encode(SelectTargetDTO(candidateId: candidateID))
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        return try await perform(request, successCodes: [200, 201, 202])
    }

    func result(jobID: UUID) async throws -> AnalysisResultDTO {
        let request = makeRequest(path: "v1/jobs/\(jobID.uuidString)/result", method: "GET")
        let result: AnalysisResultDTO = try await perform(request, successCodes: [200])
        _ = try contentURL(jobID: jobID, relativePath: result.contentPath)
        return result
    }

    func downloadContent(jobID: UUID, relativePath: String) async throws -> Data {
        let url = try contentURL(jobID: jobID, relativePath: relativePath)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        if let pairingToken = configuration.pairingToken {
            request.setValue(pairingToken, forHTTPHeaderField: "X-Stage-Lab-Pairing-Token")
        }

        do {
            let (data, response) = try await transport.send(request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw AnalysisAPIError.invalidResponse
            }
            guard httpResponse.statusCode == 200 else {
                throw AnalysisAPIError.backend(status: httpResponse.statusCode, code: "content_download_failed", message: "content download failed")
            }
            return data
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as AnalysisAPIError {
            throw error
        } catch {
            throw AnalysisAPIError.transport
        }
    }

    func contentURL(jobID: UUID, relativePath: String) throws -> URL {
        let components = relativePath.split(separator: "/", omittingEmptySubsequences: false)
        guard
            !relativePath.isEmpty,
            !relativePath.contains("\\"),
            !relativePath.hasPrefix("/"),
            !components.contains(where: { $0 == "." || $0 == ".." })
        else {
            throw AnalysisAPIError.invalidContentPath
        }
        let url = configuration.baseURL.appending(
            path: "v1/jobs/\(jobID.uuidString)/content/\(relativePath)"
        )
        guard
            url.scheme == configuration.baseURL.scheme,
            url.host == configuration.baseURL.host,
            url.port == configuration.baseURL.port
        else {
            throw AnalysisAPIError.invalidContentPath
        }
        return url
    }

    private func makeRequest(path: String, method: String) -> URLRequest {
        var request = URLRequest(url: configuration.baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        if let pairingToken = configuration.pairingToken {
            request.setValue(pairingToken, forHTTPHeaderField: "X-Stage-Lab-Pairing-Token")
        }
        return request
    }

    private func perform<T: Decodable>(
        _ request: URLRequest,
        successCodes: Set<Int>
    ) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await transport.send(request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw AnalysisAPIError.transport
        }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AnalysisAPIError.invalidResponse
        }
        guard successCodes.contains(httpResponse.statusCode) else {
            guard let envelope = try? JSONDecoder().decode(APIErrorEnvelope.self, from: data) else {
                throw AnalysisAPIError.invalidResponse
            }
            throw AnalysisAPIError.backend(
                status: httpResponse.statusCode,
                code: envelope.error.code,
                message: envelope.error.message
            )
        }
        do {
            return try AnalysisAPIClient.decoder.decode(T.self, from: data)
        } catch {
            throw AnalysisAPIError.decoding
        }
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractional.date(from: value) { return date }
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

nonisolated private struct SelectTargetDTO: Encodable {
    let candidateId: String
}

nonisolated private struct APIErrorEnvelope: Decodable {
    struct Detail: Decodable {
        let code: String
        let message: String
    }

    let error: Detail
}
