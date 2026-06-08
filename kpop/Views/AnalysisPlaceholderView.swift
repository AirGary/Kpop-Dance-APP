import SwiftUI

struct AnalysisView: View {
    @EnvironmentObject private var router: AppRouter
    let project: DanceProject

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(project.title)
                                .font(.title2.weight(.bold))
                            Text(project.sourceVideoName)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        StatusBadge(text: project.phase.title, systemImage: project.phase.systemImage, color: statusColor)
                    }

                    ProgressView(value: progress)
                        .tint(statusColor)

                    Text("\(Int(progress * 100))%")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 12) {
                    Text("分析步骤")
                        .font(.headline)

                    ForEach(Array(DanceProject.analysisSteps.enumerated()), id: \.element.id) { index, step in
                        AnalysisStepRow(
                            step: step,
                            isActive: index <= activeStepIndex,
                            isLast: index == DanceProject.analysisSteps.count - 1
                        )
                    }
                }
                .padding(16)
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
                .padding(16)
                .cardBackground()
            }
            .padding(18)
        }
        .background(AppUI.background)
        .navigationTitle("分析")
        .navigationBarTitleDisplayMode(.inline)
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
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}
