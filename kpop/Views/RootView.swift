import SwiftUI

struct RootView: View {
    @StateObject private var router = AppRouter()

    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("--ui-testing-identity-confirmation") {
            DancerPickView(project: Self.fixtureProject, initialRealAnalysisModel: Self.fixtureModel)
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

    private static let fixtureProject: DanceProject = {
        let project = DanceProject(title: "Identity UI Test", phase: .analyzing)
        project.remoteJobId = UUID().uuidString
        return project
    }()

    @MainActor private static var fixtureModel: RealAnalysisModel {
        let confirmation = IdentityConfirmation(confirmationID: "ui-confirmation", previousImagePath: "analysis/previous.jpg", candidateImagePath: "analysis/candidate.jpg", previousInterval: CandidateAppearanceInterval(startSeconds: 12, endSeconds: 14), candidateInterval: CandidateAppearanceInterval(startSeconds: 14, endSeconds: 16), candidateClusterID: "candidate-1")
        return RealAnalysisModel(service: IdentityConfirmationFixtureService(), initialState: .awaitingIdentityConfirmation(confirmation))
    }
}

private actor IdentityConfirmationFixtureService: AnalysisService {
    func startDetection(projectID: UUID) async throws -> AnalysisJobSnapshot { throw AnalysisServiceError.unknownJob(projectID) }
    func candidates(jobID: UUID) async throws -> [DancerCandidate] { [] }
    func selectTarget(jobID: UUID, candidateID: String) async throws -> AnalysisJobSnapshot { throw AnalysisServiceError.unknownJob(jobID) }
    func status(jobID: UUID) async throws -> AnalysisJobSnapshot { throw AnalysisServiceError.unknownJob(jobID) }
    func identityConfirmation(jobID: UUID) async throws -> IdentityConfirmation { throw AnalysisServiceError.unknownJob(jobID) }
    func submitIdentityConfirmation(jobID: UUID, confirmation: IdentityConfirmation, decision: IdentityDecisionValue) async throws -> AnalysisJobSnapshot { throw AnalysisServiceError.transport }
    func result(jobID: UUID) async throws -> AnalysisResultDescriptor { throw AnalysisServiceError.resultNotReady(jobID) }
}
