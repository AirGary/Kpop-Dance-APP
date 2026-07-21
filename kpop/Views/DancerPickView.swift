import SwiftUI

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
                    } else if !liveCandidates.isEmpty {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            ForEach(liveCandidates) { candidate in
                                LiveDancerOptionCard(
                                    candidate: candidate,
                                    imageURL: imageURL(for: candidate),
                                    isSelected: selectedCandidateID == candidate.id
                                ) {
                                    selectedCandidateID = candidate.id
                                }
                            }
                        }
                    } else {
                        HStack {
                            ProgressView()
                            Text("正在读取真实候选舞者…")
                                .foregroundStyle(AppUI.inkSoft)
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

    private var liveCandidates: [DancerCandidate] {
        guard let realAnalysisModel, case .awaitingTarget(let candidates) = realAnalysisModel.state else {
            return []
        }
        return candidates
    }

    private func imageURL(for candidate: DancerCandidate) -> URL? {
        guard let firstPath = candidate.representativeImagePaths.first else { return nil }
        guard let analysisAPIClient else { return nil }
        return try? analysisAPIClient.contentURL(relativePath: firstPath)
    }
}

private struct LiveDancerOptionCard: View {
    let candidate: DancerCandidate
    let imageURL: URL?
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                AsyncImage(url: imageURL) { phase in
                    switch phase {
                    case .success(let image): image.resizable().scaledToFill()
                    default:
                        ZStack { Color.black.opacity(0.08); Image(systemName: "figure.dance").font(.title) }
                    }
                }
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
