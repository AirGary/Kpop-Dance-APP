import CoreGraphics
import Testing
@testable import kpop

struct PortraitFollowGeometryTests {
    @Test
    func validTargetProducesBoundedNineBySixteenCropContainingPaddedBody() {
        let frame = PortraitFollowPlan.make(
            track: [AnalysisSpotlightKeyframe(timeSeconds: 2, x: 0.42, y: 0.12, width: 0.18, height: 0.72, confidence: 0.94)],
            at: 2
        )

        guard case .tracking(let crop) = frame else {
            Issue.record("Expected a tracking crop")
            return
        }
        #expect(abs(crop.width / crop.height - 9.0 / 16.0) < 0.0001)
        #expect(crop.minX >= 0 && crop.minY >= 0)
        #expect(crop.maxX <= 1 && crop.maxY <= 1)
        #expect(crop.contains(x: 0.42, y: 0.12))
        #expect(crop.contains(x: 0.60, y: 0.84))
    }

    @Test
    func interpolationMovesCropWithoutJumpingBetweenKeyframes() {
        let track = [
            AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.10, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 1, x: 0.50, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9)
        ]
        let first = PortraitFollowPlan.make(track: track, at: 0)
        let middle = PortraitFollowPlan.make(track: track, at: 0.5)
        let last = PortraitFollowPlan.make(track: track, at: 1)

        #expect(first.centerX < middle.centerX)
        #expect(middle.centerX < last.centerX)
    }

    @Test
    func invalidKeyframeCreatesNonInterpolableGap() {
        let track = [
            AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.10, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 1, x: .nan, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 2, x: 0.50, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9)
        ]

        #expect(PortraitFollowPlan.make(track: track, at: 1) == .fullSource)
    }

    @Test
    func invalidKeyframeBlocksTheEntireBoundedInterpolationInterval() {
        let track = [
            AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.10, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 1, x: 0.30, y: 0.10, width: 0, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 2, x: 0.50, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9)
        ]

        #expect(PortraitFollowPlan.make(track: track, at: 0.5) == .fullSource)
        #expect(PortraitFollowPlan.make(track: track, at: 1) == .fullSource)
        #expect(PortraitFollowPlan.make(track: track, at: 1.5) == .fullSource)
    }

    @Test
    func lowConfidenceInvalidAndDistantFramesFallBackToFullSource() {
        let lowConfidence = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.1, y: 0.1, width: 0.2, height: 0.7, confidence: 0.54)]
        let invalid = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: .nan, y: 0.1, width: 0.2, height: 0.7, confidence: 1)]
        let distant = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.1, y: 0.1, width: 0.2, height: 0.7, confidence: 1)]

        #expect(PortraitFollowPlan.make(track: lowConfidence, at: 0) == .fullSource)
        #expect(PortraitFollowPlan.make(track: invalid, at: 0) == .fullSource)
        #expect(PortraitFollowPlan.make(track: distant, at: 1.01) == .fullSource)
    }

    @Test
    func outOfRangeSpotlightFramesDoNotInterpolateOrTrack() {
        let track = [
            AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.10, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 1, x: 0.92, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9),
            AnalysisSpotlightKeyframe(timeSeconds: 2, x: 0.50, y: 0.10, width: 0.18, height: 0.70, confidence: 0.9)
        ]

        #expect(PortraitFollowPlan.make(track: track, at: 1) == .fullSource)
        #expect(PortraitFollowPlan.make(track: track, at: 1.5) == .fullSource)
    }

    @Test
    func projectionMapsSourceRectIntoActiveCropCoordinates() throws {
        let crop = try #require(
            PortraitFollowPlan.make(
                track: [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.2, y: 0.1, width: 0.2, height: 0.7, confidence: 0.9)],
                at: 0
            ).crop
        )
        let projected = try #require(
            PortraitFollowProjection.project(
                NormalizedRect(minX: 0.2, minY: 0.1, width: 0.2, height: 0.7),
                in: .tracking(crop)
            )
        )

        #expect(projected.minX >= 0)
        #expect(projected.minY >= 0)
        #expect(projected.maxX <= 1)
        #expect(projected.maxY <= 1)
    }

    @Test
    func projectionKeepsSourceCoordinatesWhenUsingFullSourceFallback() throws {
        let projected = try #require(
            PortraitFollowProjection.project(
                NormalizedRect(minX: 0.2, minY: 0.1, width: 0.2, height: 0.7),
                in: .fullSource
            )
        )

        #expect(projected == CGRect(x: 0.2, y: 0.1, width: 0.2, height: 0.7))
    }

    @Test
    func projectionRejectsNonPositiveSourceRectangles() {
        let crop = NormalizedRect(minX: 0, minY: 0, width: 0.5, height: 1)

        #expect(PortraitFollowProjection.project(
            NormalizedRect(minX: 0.2, minY: 0.2, width: 0, height: 0.2),
            in: .tracking(crop)
        ) == nil)
        #expect(PortraitFollowProjection.project(
            NormalizedRect(minX: 0.2, minY: 0.2, width: -0.1, height: 0.2),
            in: .fullSource
        ) == nil)
    }
}
