import Foundation

nonisolated enum JobCreationInputError: Error, Equatable, Sendable {
    case missingVideo
    case unsupportedVideoType
    case invalidDuration
    case invalidByteCount
}

nonisolated struct JobCreationInput: Equatable, Sendable {
    let request: CreateRemoteJobRequest
    let idempotencyKey: String
}

@MainActor
enum JobCreationInputFactory {
    static func make(
        project: DanceProject,
        fileManager: FileManager = .default
    ) throws -> JobCreationInput {
        guard
            let path = project.sourceVideoPath,
            !path.isEmpty,
            fileManager.fileExists(atPath: path)
        else {
            throw JobCreationInputError.missingVideo
        }
        guard project.videoDuration > 0, project.videoDuration <= 360 else {
            throw JobCreationInputError.invalidDuration
        }

        let url = URL(fileURLWithPath: path)
        let mimeType: String
        switch url.pathExtension.lowercased() {
        case "mp4": mimeType = "video/mp4"
        case "mov": mimeType = "video/quicktime"
        default: throw JobCreationInputError.unsupportedVideoType
        }

        let attributes = try fileManager.attributesOfItem(atPath: path)
        guard
            let number = attributes[.size] as? NSNumber,
            number.int64Value > 0,
            number.int64Value <= 2_147_483_648
        else {
            throw JobCreationInputError.invalidByteCount
        }

        let projectID = project.id.uuidString.lowercased()
        return JobCreationInput(
            request: CreateRemoteJobRequest(
                projectId: project.id,
                sourceFingerprint: "project:\(projectID)",
                durationSeconds: project.videoDuration,
                byteCount: number.int64Value,
                mimeType: mimeType
            ),
            idempotencyKey: "project-\(projectID)"
        )
    }
}
