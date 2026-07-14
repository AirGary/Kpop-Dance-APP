import SwiftUI
import SwiftData

struct HomeView: View {
    @Query(sort: \DanceProject.updatedAt, order: .reverse) private var projects: [DanceProject]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HomeHero(
                    projectCount: projects.count,
                    recentProjectName: projects.first?.title,
                    recommendedFocus: recommendedFocus
                )

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    MetricTile(
                        value: "\(projects.count)",
                        label: "学习项目",
                        detail: projects.isEmpty ? "从第一支舞开始" : "按最近更新时间排序",
                        icon: "square.stack.3d.up.fill",
                        accent: AppUI.violet
                    )
                    MetricTile(
                        value: practiceRateTitle,
                        label: "常用速度",
                        detail: "播放器默认练习速度",
                        icon: "speedometer",
                        accent: AppUI.cyan
                    )
                    MetricTile(
                        value: "\(practiceReadyProjects.count)",
                        label: "可练习项目",
                        detail: "已完成舞者选择",
                        icon: "figure.walk.motion",
                        accent: AppUI.lime
                    )
                    MetricTile(
                        value: "3",
                        label: "练习模式",
                        detail: "速度 / 镜像 / 循环",
                        icon: "slider.horizontal.3",
                        accent: AppUI.coral
                    )
                }

                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Dashboard",
                        title: "今天的练习安排",
                        detail: projects.isEmpty ? "导入一段固定机位舞蹈视频，系统会为你建立新的练习项目。" : "从最近更新的项目开始，继续播放器练习或完成分析流程。"
                    )

                    if projects.isEmpty {
                        emptyState
                    } else {
                        ForEach(projects) { project in
                            NavigationLink(value: route(for: project)) {
                                ProjectRow(project: project)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(20)
        }
        .background(AppUI.background)
        .navigationTitle("Stage Lab")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink(value: Route.importVideo) {
                    Image(systemName: "plus")
                }
            }
        }
    }

    private var practiceReadyProjects: [DanceProject] {
        projects.filter { $0.phase == .readyToPractice || $0.phase == .practicing }
    }

    private var recommendedFocus: String {
        if let currentProject = practiceReadyProjects.first {
            return "继续 \(currentProject.title)"
        }
        if let currentProject = projects.first {
            return "完成 \(currentProject.title) 的流程"
        }
        return "导入第一支舞蹈视频"
    }

    private var practiceRateTitle: String {
        guard let project = projects.first else { return "0.75x" }
        return project.playbackRate.title
    }

    private func route(for project: DanceProject) -> Route {
        switch project.phase {
        case .created, .analyzing, .failed:
            return .analysis(projectId: project.id)
        case .needsDancerSelection:
            return .dancerPick(projectId: project.id)
        case .readyToPractice, .practicing:
            return .practice(projectId: project.id)
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 14) {
                Image(systemName: "sparkles.rectangle.stack.fill")
                    .font(.title2)
                    .foregroundStyle(AppUI.violet)
                    .frame(width: 48, height: 48)
                    .background(AppUI.violet.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("还没有项目")
                        .font(.headline)
                        .foregroundStyle(AppUI.ink)
                    Text("先导入一段固定机位舞蹈视频，开始建立第一条练习时间轴。")
                        .font(.subheadline)
                        .foregroundStyle(AppUI.inkSoft)
                }
            }

            NavigationLink(value: Route.importVideo) {
                Label("导入视频并开始练习", systemImage: "plus.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(AppUI.panelPadding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardBackground(.primary)
    }
}

private struct HomeHero: View {
    let projectCount: Int
    let recentProjectName: String?
    let recommendedFocus: String

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 32, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            AppUI.ink,
                            AppUI.violet,
                            AppUI.cyan
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            Circle()
                .fill(.white.opacity(0.13))
                .frame(width: 220, height: 220)
                .offset(x: 120, y: -70)

            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    StatusBadge(text: "Practice Console", systemImage: "music.note", color: .white)
                    Spacer()
                    Text("\(projectCount) 个项目")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.84))
                }

                VStack(alignment: .leading, spacing: 10) {
                    Text("把舞蹈视频整理成稳定、可重复的练习流程")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("当前推荐：\(recommendedFocus)")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.86))

                    if let recentProjectName {
                        Text("最近项目：\(recentProjectName)")
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.72))
                    }
                }

                HStack(spacing: 12) {
                    HeroFact(title: "主流程", value: "导入 / 分析 / 练习")
                    HeroFact(title: "训练模式", value: "速度 / 镜像 / 循环")
                }
            }
            .padding(24)
        }
        .frame(height: 240)
    }
}

private struct ProjectRow: View {
    let project: DanceProject

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: project.phase.systemImage)
                    .font(.title3)
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(statusColor, in: RoundedRectangle(cornerRadius: 14, style: .continuous))

                VStack(alignment: .leading, spacing: 6) {
                    Text(project.title)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(AppUI.ink)
                        .lineLimit(1)

                    Text(project.sourceVideoName)
                        .font(.subheadline)
                        .foregroundStyle(AppUI.inkSoft)
                        .lineLimit(1)
                }

                Spacer()

                StatusBadge(text: project.phase.title, systemImage: project.phase.systemImage, color: statusColor)
            }

            Divider()
                .overlay(AppUI.divider)

            HStack(spacing: 18) {
                StageInfoRow(
                    title: "目标舞者",
                    value: project.selectedDancerName ?? "待选择",
                    systemImage: "figure.dance"
                )
                StageInfoRow(
                    title: "视频状态",
                    value: project.sourceVideoPath == nil ? "待导入" : "已就绪",
                    systemImage: project.sourceVideoPath == nil ? "tray" : "checkmark.seal"
                )
            }

            Text("最近更新：\(project.updatedAt.formatted(date: .abbreviated, time: .shortened))")
                .font(.caption)
                .foregroundStyle(AppUI.inkSoft)
        }
        .padding(AppUI.panelPadding)
        .cardBackground(.primary)
    }

    private var statusColor: Color {
        switch project.phase {
        case .created: .gray
        case .analyzing: AppUI.violet
        case .needsDancerSelection: AppUI.amber
        case .readyToPractice: AppUI.lime
        case .practicing: AppUI.cyan
        case .failed: AppUI.coral
        }
    }
}

#Preview("Home Dashboard") {
    NavigationStack {
        HomeView()
    }
    .modelContainer(PreviewProjects.previewContainer())
}

#Preview("Home Empty") {
    NavigationStack {
        HomeView()
    }
    .modelContainer(PreviewProjects.previewContainer(projects: []))
}
