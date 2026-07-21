import SwiftUI
import UIKit

enum DancerPickPresentationState: Equatable {
    case loading
    case candidates([DancerCandidate])
    case failed(String, recoverable: Bool)
}

func dancerPickPresentationState(for state: RealAnalysisState) -> DancerPickPresentationState {
    switch state {
    case .awaitingTarget(let candidates):
        return .candidates(candidates)
    case .failed(let message, let recoverable):
        return .failed(message, recoverable: recoverable)
    default:
        return .loading
    }
}

struct DancerPickView: View {
    @EnvironmentObject private var router: AppRouter
    @Environment(\.analysisService) private var analysisService
    @Environment(\.analysisAPIClient) private var analysisAPIClient
    @Environment(\.analysisPackageDownloader) private var analysisPackageDownloader
    let project: DanceProject
    @State private var selectedDancer: DancerOption?
    @State private var selectedCandidateID: String?
    @State private var realAnalysisModel: RealAnalysisModel?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                DancerPreview(selectedDancer: selectedDancer)

                VStack(alignment: .leading, spacing: 12) {
                    StageSectionHeader(
                        eyebrow: "Selection",
                        title: "选择目标舞者",
                        detail: "锁定本次主要学习对象。完成后会直接生成新的练习时间轴。"
                    )

                    if realAnalysisModel == nil {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            ForEach(DanceProject.dancerOptions) { dancer in
                                DancerOptionCard(
                                    dancer: dancer,
                                    isSelected: selectedDancer == dancer
                                ) {
                                    selectedDancer = dancer
                                }
                            }
                        }
                    } else if let realAnalysisModel {
                        switch dancerPickPresentationState(for: realAnalysisModel.state) {
                        case .candidates(let candidates) where !candidates.isEmpty:
                            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                                ForEach(candidates) { candidate in
                                    LiveDancerOptionCard(
                                        candidate: candidate,
                                        analysisAPIClient: analysisAPIClient,
                                        jobID: remoteJobUUID,
                                        isSelected: selectedCandidateID == candidate.id
                                    ) {
                                        selectedCandidateID = candidate.id
                                    }
                                }
                            }
                        case .candidates:
                            Text("尚未得到有效候选舞者，请重新检测。")
                                .foregroundStyle(AppUI.inkSoft)
                        case .failed(let message, let recoverable):
                            VStack(alignment: .leading, spacing: 10) {
                                Label(message, systemImage: "exclamationmark.triangle.fill")
                                    .foregroundStyle(.red)
                                if recoverable {
                                    Button("重试读取状态") {
                                        Task { await realAnalysisModel.start(project: project) }
                                    }
                                    .buttonStyle(.bordered)
                                }
                            }
                        case .loading:
                            HStack {
                                ProgressView()
                                Text("正在读取真实候选舞者…")
                                    .foregroundStyle(AppUI.inkSoft)
                            }
                        }
                    }
                }
                .padding(AppUI.panelPadding)
                .cardBackground()

                VStack(spacing: 10) {
                    Button {
                        if let selectedCandidateID, let realAnalysisModel {
                            Task {
                                await realAnalysisModel.select(candidateID: selectedCandidateID, project: project)
                                if case .resultReady = realAnalysisModel.state {
                                    project.phase = .readyToPractice
                                    project.updatedAt = Date()
                                    router.replaceTop(with: .practice(projectId: project.id))
                                }
                            }
                        } else if let selectedDancer {
                            project.selectedDancerName = selectedDancer.name
                            project.phase = .readyToPractice
                            project.updatedAt = Date()
                            router.replaceTop(with: .practice(projectId: project.id))
                        }
                    } label: {
                        Label(realAnalysisModel == nil ? "生成练习时间轴" : "提交目标舞者分析", systemImage: "timeline.selection")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedDancer == nil && selectedCandidateID == nil)

                    Button {
                        project.phase = .analyzing
                        project.updatedAt = Date()
                        router.replaceTop(with: .analysis(projectId: project.id))
                    } label: {
                        Label("重新检测", systemImage: "arrow.clockwise")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                .padding(AppUI.panelPadding)
                .cardBackground()
            }
            .padding(20)
        }
        .background(AppUI.background)
        .navigationTitle("选择舞者")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: project.remoteJobId) {
            guard
                let analysisService,
                project.remoteJobId != nil,
                realAnalysisModel == nil
            else { return }
            let model = RealAnalysisModel(
                service: analysisService,
                packageDownloader: analysisPackageDownloader,
                packageStore: try? AnalysisPackageStore.applicationSupport()
            )
            realAnalysisModel = model
            await model.start(project: project)
        }
    }

    private var remoteJobUUID: UUID? {
        guard let remoteJobId = project.remoteJobId else { return nil }
        return UUID(uuidString: remoteJobId)
    }
}

private struct LiveDancerOptionCard: View {
    let candidate: DancerCandidate
    let analysisAPIClient: AnalysisAPIClient?
    let jobID: UUID?
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                AuthenticatedCandidateImage(
                    client: analysisAPIClient,
                    jobID: jobID,
                    path: candidate.representativeImagePaths.first
                )
                .frame(height: 120)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

                HStack {
                    Text(candidate.displayName).font(.headline)
                    Spacer()
                    Text("\(Int(candidate.confidence * 100))%")
                        .font(.caption.monospacedDigit().weight(.bold))
                        .foregroundStyle(AppUI.violet)
                }
                Text(candidate.positionLabel)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
            .padding(10)
            .background(isSelected ? AppUI.violet.opacity(0.12) : AppUI.panel, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(isSelected ? AppUI.violet : AppUI.divider, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct AuthenticatedCandidateImage: View {
    let client: AnalysisAPIClient?
    let jobID: UUID?
    let path: String?
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    Color.black.opacity(0.08)
                    Image(systemName: "figure.dance").font(.title)
                }
            }
        }
        .task(id: "\(jobID?.uuidString ?? "missing")-\(path ?? "missing")") {
            guard let client, let jobID, let path else { return }
            guard let data = try? await client.downloadContent(jobID: jobID, relativePath: path) else { return }
            image = UIImage(data: data)
        }
    }
}

private struct DancerPreview: View {
    let selectedDancer: DancerOption?

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [.black.opacity(0.88), AppUI.violet.opacity(0.72), AppUI.cyan.opacity(0.48)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            HStack(alignment: .bottom, spacing: 16) {
                ForEach(DanceProject.dancerOptions) { dancer in
                    VStack(spacing: 6) {
                        Image(systemName: "figure.dance")
                            .font(.system(size: selectedDancer == dancer ? 38 : 30))
                        Text("\(dancer.id)")
                            .font(.caption.weight(.bold))
                    }
                    .foregroundStyle(selectedDancer == dancer ? .yellow : .white.opacity(0.75))
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, dancer.id == 2 ? 28 : 12)
                }
            }
            .padding(.horizontal, 18)
        }
        .frame(height: 230)
        .accessibilityLabel("舞者检测预览")
    }
}

private struct DancerOptionCard: View {
    let dancer: DancerOption
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("\(dancer.id)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 26, height: 26)
                        .background(isSelected ? AppUI.violet : Color.secondary, in: Circle())

                    Spacer()

                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                }

                Text(dancer.name)
                    .font(.headline)
                    .foregroundStyle(AppUI.ink)

                Text(dancer.position)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                isSelected ? AppUI.violet.opacity(0.12) : AppUI.panel,
                in: RoundedRectangle(cornerRadius: 20, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(isSelected ? AppUI.violet : AppUI.divider, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
