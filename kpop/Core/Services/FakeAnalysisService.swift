import Foundation

actor FakeAnalysisService: AnalysisService {
    private struct JobRecord {
        var snapshot: AnalysisJobSnapshot
        let candidates: [DancerCandidate]
        var selectedCandidateID: String?
        var result: AnalysisResultDescriptor?
    }

    private var jobs: [UUID: JobRecord] = [:]

    func startDetection(projectID: UUID) throws -> AnalysisJobSnapshot {
        let jobID = projectID
        if let existing = jobs[jobID] {
            return existing.snapshot
        }

        var snapshot = AnalysisJobSnapshot(id: jobID, projectID: projectID)
        try advance(
            &snapshot,
            through: [
                (.preparing, 0.05),
                (.uploading, 0.15),
                (.uploaded, 0.25),
                (.detecting, 0.4),
                (.awaitingTarget, 0.5)
            ]
        )
        jobs[jobID] = JobRecord(
            snapshot: snapshot,
            candidates: Self.defaultCandidates
        )
        return snapshot
    }

    func candidates(jobID: UUID) throws -> [DancerCandidate] {
        guard let job = jobs[jobID] else {
            throw AnalysisServiceError.unknownJob(jobID)
        }
        return job.candidates
    }

    func selectTarget(jobID: UUID, candidateID: String) throws -> AnalysisJobSnapshot {
        guard var job = jobs[jobID] else {
            throw AnalysisServiceError.unknownJob(jobID)
        }
        guard job.candidates.contains(where: { $0.id == candidateID }) else {
            throw AnalysisServiceError.candidateNotFound(candidateID)
        }

        try advance(
            &job.snapshot,
            through: [
                (.queued, 0.55),
                (.analyzing, 0.75),
                (.resultReady, 0.9),
                (.importing, 0.95),
                (.completed, 1)
            ]
        )
        job.selectedCandidateID = candidateID
        job.result = AnalysisResultDescriptor(
            jobID: jobID,
            projectID: job.snapshot.projectID,
            schemaVersion: 1,
            packageName: "result-v1.bin"
        )
        jobs[jobID] = job
        return job.snapshot
    }

    func status(jobID: UUID) throws -> AnalysisJobSnapshot {
        guard let job = jobs[jobID] else {
            throw AnalysisServiceError.unknownJob(jobID)
        }
        return job.snapshot
    }

    func result(jobID: UUID) throws -> AnalysisResultDescriptor {
        guard let job = jobs[jobID] else {
            throw AnalysisServiceError.unknownJob(jobID)
        }
        guard let result = job.result, job.snapshot.state == .completed else {
            throw AnalysisServiceError.resultNotReady(jobID)
        }
        return result
    }

    private func advance(
        _ snapshot: inout AnalysisJobSnapshot,
        through steps: [(state: AnalysisJobState, progress: Double)]
    ) throws {
        for step in steps {
            try AnalysisStateMachine.transition(&snapshot, to: step.state)
            snapshot.progress = step.progress
        }
    }

    private nonisolated static let defaultCandidates = [
        DancerCandidate(
            id: "dancer-left",
            displayName: "Dancer 1",
            positionLabel: "左侧",
            confidence: 0.94
        ),
        DancerCandidate(
            id: "dancer-center",
            displayName: "Dancer 2",
            positionLabel: "中间",
            confidence: 0.97
        ),
        DancerCandidate(
            id: "dancer-right",
            displayName: "Dancer 3",
            positionLabel: "右侧",
            confidence: 0.92
        )
    ]
}
