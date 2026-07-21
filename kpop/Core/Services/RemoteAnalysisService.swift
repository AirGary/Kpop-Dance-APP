import Foundation

actor RemoteAnalysisService: AnalysisService, AnalysisPackageDownloader {
    private let client: AnalysisAPIClient

    init(client: AnalysisAPIClient) {
        self.client = client
    }

    func startDetection(projectID: UUID) async throws -> AnalysisJobSnapshot {
        throw AnalysisServiceError.unknownJob(projectID)
    }

    func candidates(jobID: UUID) async throws -> [DancerCandidate] {
        do {
            let values = try await client.dancers(jobID: jobID)
            return values.enumerated().map { index, value in
                DancerCandidate(
                    id: value.candidateId,
                    displayName: "舞者 \(index + 1)",
                    positionLabel: Self.positionLabel(for: value.boxSummary),
                    confidence: value.confidence,
                    representativeImagePaths: value.representativeImagePaths,
                    appearanceIntervals: value.appearanceIntervals.map {
                        CandidateAppearanceInterval(startSeconds: $0.startSeconds, endSeconds: $0.endSeconds)
                    },
                    boxSummary: CandidateBoxSummary(
                        x: value.boxSummary.x,
                        y: value.boxSummary.y,
                        width: value.boxSummary.width,
                        height: value.boxSummary.height
                    )
                )
            }
        } catch {
            throw map(error)
        }
    }

    func selectTarget(jobID: UUID, candidateID: String) async throws -> AnalysisJobSnapshot {
        do {
            let remote = try await client.selectTarget(
                jobID: jobID,
                candidateID: candidateID,
                idempotencyKey: Self.selectionKey(jobID: jobID, candidateID: candidateID)
            )
            return Self.snapshot(from: remote)
        } catch {
            throw map(error)
        }
    }

    func status(jobID: UUID) async throws -> AnalysisJobSnapshot {
        do {
            return Self.snapshot(from: try await JobsAPIClient(configuration: client.configuration, transport: client.transport).job(id: jobID))
        } catch {
            throw map(error)
        }
    }

    func result(jobID: UUID) async throws -> AnalysisResultDescriptor {
        do {
            let projectID = try await status(jobID: jobID).projectID
            let result = try await client.result(jobID: jobID)
            return AnalysisResultDescriptor(
                jobID: jobID,
                projectID: projectID,
                schemaVersion: result.schemaVersion,
                packageName: result.contentPath,
                sha256: result.sha256,
                byteCount: result.byteCount
            )
        } catch {
            throw map(error)
        }
    }

    func downloadPackage(result: AnalysisResultDescriptor) async throws -> Data {
        do {
            return try await client.downloadContent(jobID: result.jobID, relativePath: result.packageName)
        } catch {
            throw map(error)
        }
    }

    static func selectionKey(jobID: UUID, candidateID: String) -> String {
        "target-\(jobID.uuidString.lowercased())-\(candidateID)"
    }

    private static func snapshot(from job: RemoteJob) -> AnalysisJobSnapshot {
        AnalysisJobSnapshot(
            id: job.id,
            projectID: job.projectId,
            state: job.state,
            progress: job.progress,
            errorCode: job.errorCode,
            updatedAt: job.updatedAt
        )
    }

    private static func positionLabel(for box: AnalysisBoxSummaryDTO) -> String {
        let center = box.x + box.width / 2
        if center < 0.34 { return "画面左侧" }
        if center > 0.66 { return "画面右侧" }
        return "画面中部"
    }

    private func map(_ error: Error) -> Error {
        if let error = error as? AnalysisServiceError { return error }
        if let error = error as? AnalysisAPIError {
            switch error {
            case .backend(_, let code, _): return AnalysisServiceError.backend(code)
            case .transport: return AnalysisServiceError.transport
            case .invalidContentPath, .invalidResponse, .decoding: return AnalysisServiceError.invalidResponse
            }
        }
        return AnalysisServiceError.transport
    }
}
