import SwiftUI

struct RootView: View {
    @StateObject private var router = AppRouter()

    var body: some View {
        NavigationStack(path: $router.path) {
            HomeView()
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .importVideo:
                        ImportView()
                    case .analysis(let projectId):
                        ProjectRouteView(projectId: projectId) { project in
                            AnalysisView(project: project)
                        }
                    case .dancerPick(let projectId):
                        ProjectRouteView(projectId: projectId) { project in
                            DancerPickView(project: project)
                        }
                    case .practice(let projectId):
                        ProjectRouteView(projectId: projectId) { project in
                            PracticeView(project: project)
                        }
                    }
                }
        }
        .environmentObject(router)
    }
}
