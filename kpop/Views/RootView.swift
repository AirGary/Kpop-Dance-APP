import SwiftUI

struct RootView: View {
    @StateObject private var router = AppRouter()

    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("--ui-testing-identity-confirmation") {
            IdentityConfirmationView(
                confirmation: IdentityConfirmation(
                    confirmationID: "ui-confirmation",
                    previousImagePath: "analysis/previous.jpg",
                    candidateImagePath: "analysis/candidate.jpg",
                    previousInterval: CandidateAppearanceInterval(startSeconds: 12, endSeconds: 14),
                    candidateInterval: CandidateAppearanceInterval(startSeconds: 14, endSeconds: 16),
                    candidateClusterID: "candidate-1"
                ),
                client: nil,
                jobID: nil
            ) { _ in false }
        } else {
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
}
