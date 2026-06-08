import SwiftUI
import SwiftData

struct ProjectRouteView<Content: View>: View {
    private let content: (DanceProject) -> Content

    @Query private var projects: [DanceProject]

    init(projectId: UUID, @ViewBuilder content: @escaping (DanceProject) -> Content) {
        self.content = content
        _projects = Query(filter: #Predicate<DanceProject> { project in
            project.id == projectId
        })
    }

    var body: some View {
        if let project = projects.first {
            content(project)
        } else {
            ContentUnavailableView {
                Label("项目不存在", systemImage: "questionmark.folder")
            } description: {
                Text("该项目可能已被删除。")
            }
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

