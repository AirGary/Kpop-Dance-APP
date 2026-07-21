import Testing
@testable import kpop

struct DancerPickPresentationTests {
    @Test
    func recoverableFailureIsPresentedAsRetryableError() {
        let state = dancerPickPresentationState(
            for: .failed("worker_unavailable", recoverable: true)
        )

        #expect(state == .failed("worker_unavailable", recoverable: true))
    }
}
