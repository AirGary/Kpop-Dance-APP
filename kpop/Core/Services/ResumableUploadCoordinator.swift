import Foundation

nonisolated enum ResumableUploadError: Error, Equatable, Sendable {
    case invalidDuration
    case invalidServerOffset
    case stalledUpload
}

nonisolated enum UploadProgress: Equatable, Sendable {
    case compressing
    case hashing
    case uploading(
        uploadID: UUID,
        confirmedBytes: Int64,
        totalBytes: Int64,
        expiresAt: Date
    )
    case validating
}

nonisolated struct UploadCompletion: Equatable, Sendable {
    let uploadID: UUID
    let jobID: UUID
}

nonisolated struct ResumableUploadCoordinator: Sendable {
    private let apiProvider: @Sendable (Bool) -> UploadAPIClient
    private let compressor: VideoCompressionService
    private let staging: UploadStagingStore

    init(
        apiProvider: @escaping @Sendable (Bool) -> UploadAPIClient,
        compressor: VideoCompressionService,
        staging: UploadStagingStore
    ) {
        self.apiProvider = apiProvider
        self.compressor = compressor
        self.staging = staging
    }

    static func live(configuration: JobsAPIConfiguration) throws -> ResumableUploadCoordinator {
        ResumableUploadCoordinator(
            apiProvider: { allowsCellular in
                UploadAPIClient(
                    configuration: configuration,
                    transport: UploadNetworkPolicy.transport(allowsCellular: allowsCellular)
                )
            },
            compressor: .live,
            staging: try .applicationSupport()
        )
    }

    func run(
        projectID: UUID,
        sourceFingerprint: String,
        durationSeconds: Double,
        sourceURL: URL,
        allowsCellular: Bool,
        onProgress: @escaping @Sendable (UploadProgress) async -> Void
    ) async throws -> UploadCompletion {
        guard durationSeconds > 0, durationSeconds <= 360 else {
            throw ResumableUploadError.invalidDuration
        }

        if !staging.exists(projectID: projectID) {
            await onProgress(.compressing)
            let destination = try staging.prepareFileURL(projectID: projectID)
            do {
                try await compressor.compress(
                    sourceURL: sourceURL,
                    destinationURL: destination
                )
            } catch {
                try? staging.delete(projectID: projectID)
                throw error
            }
        }

        await onProgress(.hashing)
        let totalBytes = try staging.byteCount(projectID: projectID)
        let digest = try staging.sha256(projectID: projectID)
        let keySuffix = projectID.uuidString.lowercased()
        let api = apiProvider(allowsCellular)
        let session = try await api.create(
            UploadCreateInput(
                projectID: projectID,
                sourceFingerprint: sourceFingerprint,
                durationSeconds: durationSeconds,
                byteCount: totalBytes,
                mimeType: "video/mp4",
                sha256: digest
            ),
            idempotencyKey: "upload-\(keySuffix)"
        )
        var confirmedBytes = try await api.offset(uploadURL: session.uploadURL)
        guard confirmedBytes >= 0, confirmedBytes <= totalBytes else {
            throw ResumableUploadError.invalidServerOffset
        }

        await onProgress(.uploading(
            uploadID: session.uploadID,
            confirmedBytes: confirmedBytes,
            totalBytes: totalBytes,
            expiresAt: session.expiresAt
        ))
        while confirmedBytes < totalBytes {
            let remaining = totalBytes - confirmedBytes
            let requestedCount = Int(min(Int64(session.chunkSize), remaining))
            let chunk = try staging.readChunk(
                projectID: projectID,
                offset: confirmedBytes,
                count: requestedCount
            )
            guard chunk.count == requestedCount else {
                throw UploadStagingError.invalidByteCount
            }
            let result = try await api.putChunk(
                uploadURL: session.uploadURL,
                data: chunk,
                start: confirmedBytes,
                total: totalBytes
            )
            guard result.offset > confirmedBytes, result.offset <= totalBytes else {
                throw ResumableUploadError.stalledUpload
            }
            confirmedBytes = result.offset
            await onProgress(.uploading(
                uploadID: session.uploadID,
                confirmedBytes: confirmedBytes,
                totalBytes: totalBytes,
                expiresAt: session.expiresAt
            ))
        }

        await onProgress(.validating)
        let job = try await api.complete(
            uploadID: session.uploadID,
            idempotencyKey: "upload-complete-\(keySuffix)"
        )
        try staging.delete(projectID: projectID)
        return UploadCompletion(uploadID: session.uploadID, jobID: job.id)
    }
}
