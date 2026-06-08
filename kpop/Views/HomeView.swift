import SwiftUI
import SwiftData

struct HomeView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \DanceProject.updatedAt, order: .reverse) private var projects: [DanceProject]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HomeHero(projectCount: projects.count)

                HStack(spacing: 10) {
                    MiniStat(value: "5", label: "页面")
                    MiniStat(value: "3", label: "速度")
                    MiniStat(value: "AI", label: "节点")
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("学习项目")
                        .font(.title3.weight(.semibold))

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
            .padding(18)
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

    private func deleteProjects(at offsets: IndexSet) {
        for index in offsets {
            modelContext.delete(projects[index])
        }
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
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: "sparkles.rectangle.stack")
                .font(.largeTitle)
                .foregroundStyle(AppUI.violet)

            Text("还没有项目")
                .font(.headline)

            Text("导入一段固定机位舞蹈视频，开始建立第一条练习时间轴。")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            NavigationLink(value: Route.importVideo) {
                Label("导入视频", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardBackground()
    }
}

private struct HomeHero: View {
    let projectCount: Int

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 8)
                .fill(
                    LinearGradient(
                        colors: [AppUI.ink, AppUI.violet, AppUI.cyan],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 10) {
                    StatusBadge(text: "K-pop Dance", systemImage: "music.note", color: .white)

                    Text("把舞蹈视频变成练习时间轴")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("\(projectCount) 个项目")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.8))
                }

                Spacer()

                Image(systemName: "figure.dance")
                    .font(.system(size: 68))
                    .foregroundStyle(.white.opacity(0.9))
            }
            .padding(20)
        }
        .frame(height: 190)
    }
}

private struct ProjectRow: View {
    let project: DanceProject

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: project.phase.systemImage)
                .font(.title3)
                .foregroundStyle(.white)
                .frame(width: 38, height: 38)
                .background(statusColor, in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 5) {
                Text(project.title)
                    .font(.headline)
                    .lineLimit(1)

                HStack(spacing: 8) {
                    Text(project.phase.title)
                    Text(project.updatedAt, style: .date)
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)

                if let selectedDancerName = project.selectedDancerName {
                    Text("目标舞者：\(selectedDancerName)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .cardBackground()
    }

    private var statusColor: Color {
        switch project.phase {
        case .created: .gray
        case .analyzing: .blue
        case .needsDancerSelection: .orange
        case .readyToPractice: .green
        case .practicing: .purple
        case .failed: .red
        }
    }
}
