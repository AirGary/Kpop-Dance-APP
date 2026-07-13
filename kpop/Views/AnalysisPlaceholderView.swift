import SwiftUI

struct AnalysisView: View {
    @EnvironmentObject private var router: AppRouter
    @Environment(\.jobsAPIClient) private var jobsAPIClient
    @State private var connectionModel = AnalysisConnectionModel()
    let project: DanceProject

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Analysis",
                        title: project.title,
                        detail: "整理关键帧、节拍和动作节点，为后续舞者选择与练习时间轴做准备。"
                    )

                    HStack {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(project.sourceVideoName)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(AppUI.inkSoft)
                        }

                        Spacer()

                        StatusBadge(text: project.phase.title, systemImage: project.phase.systemImage, color: statusColor)
                    }

                    ProgressView(value: progress)
                        .tint(statusColor)

                    Text("分析进度 \(Int(progress * 100))%")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppUI.inkSoft)
                }
                .padding(AppUI.panelPadding)
                .cardBackground()

                localBackendCard

                VStack(alignment: .leading, spacing: 12) {
                    StageSectionHeader(
                        eyebrow: "Pipeline",
                        title: "分析步骤",
                        detail: "当前以轻量流程模拟真实分析阶段，界面会保持和后续播放器一致的训练工具风格。"
                    )

                    ForEach(Array(DanceProject.analysisSteps.enumerated()), id: \.element.id) { index, step in
                        AnalysisStepRow(
                            step: step,
                            isActive: index <= activeStepIndex,
                            isLast: index == DanceProject.analysisSteps.count - 1
                        )
                    }
                }
                .padding(AppUI.panelPadding)
                .cardBackground()

                VStack(spacing: 10) {
                    Button(project.phase == .failed ? "重试分析" : "开始/继续分析") {
                        setPhase(.analyzing)
                    }
                    .buttonStyle(.bordered)
                    .frame(maxWidth: .infinity)

                    Button {
                        setPhase(.needsDancerSelection)
                        router.replaceTop(with: .dancerPick(projectId: project.id))
                    } label: {
                        Label("完成分析，选择舞者", systemImage: "figure.dance")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button(role: .destructive) {
                        setPhase(.failed)
                    } label: {
                        Label("标记分析失败", systemImage: "exclamationmark.triangle")
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
        .navigationTitle("分析")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var localBackendCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            StageSectionHeader(
                eyebrow: "Local API",
                title: "云分析任务连接",
                detail: "当前只发送视频元数据，不会上传视频。真实 AI 分析将在后续阶段接入。"
            )

            switch connectionModel.state {
            case .idle:
                connectionButton(title: "创建云分析任务")
            case .loading:
                HStack(spacing: 10) {
                    ProgressView()
                    Text("正在连接本地后端…")
                        .font(.subheadline.weight(.semibold))
                }
            case .connected(let job):
                HStack {
                    StatusBadge(text: job.state.rawValue, systemImage: "checkmark.icloud", color: .green)
                    Spacer()
                    Text(String(job.id.uuidString.prefix(8)))
                        .font(.caption.monospaced().weight(.semibold))
                        .foregroundStyle(AppUI.inkSoft)
                }
                ProgressView(value: job.progress)
                    .tint(.green)
            case .failed(let message):
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.red)
                connectionButton(title: "重新连接")
            }

            if jobsAPIClient == nil {
                Text("本地 API 仅在 Debug 模拟器版本启用。")
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .padding(AppUI.panelPadding)
        .cardBackground()
    }

    private func connectionButton(title: String) -> some View {
        Button {
            guard let jobsAPIClient else { return }
            Task {
                await connectionModel.connect(project: project, client: jobsAPIClient)
            }
        } label: {
            Label(title, systemImage: "cloud.fill")
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .disabled(jobsAPIClient == nil)
    }

    private var progress: Double {
        switch project.phase {
        case .created: 0.1
        case .analyzing: 0.55
        case .needsDancerSelection: 1.0
        case .readyToPractice, .practicing: 1.0
        case .failed: 0.35
        }
    }

    private var activeStepIndex: Int {
        switch project.phase {
        case .created: 0
        case .analyzing: 2
        case .needsDancerSelection, .readyToPractice, .practicing: 3
        case .failed: 1
        }
    }

    private var statusColor: Color {
        switch project.phase {
        case .created: .gray
        case .analyzing: AppUI.violet
        case .needsDancerSelection: .orange
        case .readyToPractice, .practicing: .green
        case .failed: .red
        }
    }

    private func setPhase(_ phase: ProjectPhase) {
        project.phase = phase
        project.updatedAt = Date()
    }
}

private struct AnalysisStepRow: View {
    let step: AnalysisStep
    let isActive: Bool
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 6) {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(isActive ? AppUI.cyan : .secondary)

                if !isLast {
                    Rectangle()
                        .fill(isActive ? AppUI.cyan.opacity(0.45) : Color.secondary.opacity(0.18))
                        .frame(width: 2, height: 30)
                }
            }

            Image(systemName: step.systemImage)
                .frame(width: 28, height: 28)
                .foregroundStyle(isActive ? AppUI.violet : .secondary)

            VStack(alignment: .leading, spacing: 3) {
                Text(step.title)
                    .font(.subheadline.weight(.semibold))
                Text(step.detail)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .padding(.vertical, 4)
    }
}
