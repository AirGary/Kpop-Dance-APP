import Testing
@testable import kpop

@MainActor
struct ProjectModelTests {
    @Test
    func projectPhaseRoundTripsThroughPersistenceValue() {
        let project = DanceProject(title: "Test", phase: .needsDancerSelection)

        #expect(project.phaseRawValue == ProjectPhase.needsDancerSelection.rawValue)
        #expect(project.phase == .needsDancerSelection)
    }

    @Test
    func unsupportedPlaybackRateFallsBackToNormal() {
        let project = DanceProject(title: "Test", defaultPlaybackRate: 1.25)

        #expect(project.playbackRate == .normal)
    }
}
