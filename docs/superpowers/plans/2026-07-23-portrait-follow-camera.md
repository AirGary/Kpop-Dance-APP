# Portrait Follow Camera Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the iOS practice player render a 9:16, full-body-priority follow crop for the selected dancer using the existing Analysis Package spotlight and pose tracks.

**Architecture:** A pure Swift domain module converts normalized spotlight keyframes into safe 9:16 crop and fallback render plans. An AVFoundation composition builder turns that plan into crop and transform ramps on the player item, so the video pixels, skeleton, boxes, and mirror presentation share one mapping. PracticeView owns asynchronous item preparation and continues to play the original item when a package or rendering plan is unavailable.

**Tech Stack:** Swift 6, SwiftUI, AVFoundation, AVKit, Core Animation, Swift Testing, iPhone 17 Pro Max iOS 26.5 Simulator.

## Global Constraints

- Test only on iPhone 17 Pro Max, iOS 26.5, UDID `DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA`.
- Do not add iOS 27 compatibility work.
- Do not alter RTMDet-m, ByteTrack, RTMPose-m, backend API, Analysis Package schema, Google Cloud, or model weights.
- Preserve and consume all existing full-body `pose-track.json` keypoints and `spotlight-track.json` frames.
- Use target aspect ratio `9.0 / 16.0`; a locked crop must keep the padded target box inside source bounds.
- Below confidence `0.55`, absent/invalid tracking data, or a gap larger than `1.0` second, fall back to a letterboxed full-source frame.
- Keep original video, result package bytes, existing playback speed, loop, and mirror behavior unchanged.

---

## File Structure

- Create `kpop/Domain/Practice/PortraitFollowGeometry.swift`: pure normalized rectangle validation, full-body-safe crop calculation, keyframe interpolation, and fallback plans.
- Create `kpop/Domain/Practice/PortraitFollowComposition.swift`: converts a render plan plus AVAsset video track into AVMutableVideoComposition crop/transform instructions.
- Create `kpop/Views/PortraitFollowPlayerView.swift`: `UIViewRepresentable` backed by `AVPlayerLayer` with explicit 9:16 presentation and mirror support.
- Modify `kpop/Views/PracticePlaceholderView.swift`: asynchronously prepare an item with a portrait composition, pass the render plan into the overlay, use the 9:16 player, and display a non-blocking fallback status.
- Modify `kpop/Views/PracticePlayerView.swift`: remove the direct `VideoPlayer` implementation after callers move to `PortraitFollowPlayerView`.
- Create `kpopTests/PortraitFollowGeometryTests.swift`: deterministic crop, interpolation, invalid-input, full-body, and fallback tests.
- Create `kpopTests/PortraitFollowCompositionTests.swift`: test render-plan-to-composition instruction generation with a generated local video track.
- Modify `kpopTests/AnalysisPackageTests.swift`: assert complete pose keypoints remain decoded and usable by the follow geometry.
- Modify `docs/PROJECT_STATUS.md`: record the actual implementation, test evidence, 26.5-only scope, and any simulator-only limitations after verification.

## Task 1: Portrait Follow Geometry

**Files:**
- Create: `kpop/Domain/Practice/PortraitFollowGeometry.swift`
- Create: `kpopTests/PortraitFollowGeometryTests.swift`
- Modify: `kpopTests/AnalysisPackageTests.swift`

**Interfaces:**
- Consumes: `AnalysisSpotlightKeyframe`, `AnalysisPoseFrame` from `kpop/Domain/Analysis/AnalysisPackage.swift`.
- Produces: `PortraitFollowPlan.make(track:at:) -> PortraitFollowFrame` for AVFoundation and SwiftUI callers.
- Produces: `PortraitFollowProjection.project(_:) -> CGRect?` for drawing all analysis overlays in the active crop coordinate space.

- [ ] **Step 1: Write failing geometry tests**

```swift
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
    func lowConfidenceInvalidAndDistantFramesFallBackToFullSource() {
        let lowConfidence = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.1, y: 0.1, width: 0.2, height: 0.7, confidence: 0.54)]
        let invalid = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: .nan, y: 0.1, width: 0.2, height: 0.7, confidence: 1)]
        let distant = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.1, y: 0.1, width: 0.2, height: 0.7, confidence: 1)]

        #expect(PortraitFollowPlan.make(track: lowConfidence, at: 0) == .fullSource)
        #expect(PortraitFollowPlan.make(track: invalid, at: 0) == .fullSource)
        #expect(PortraitFollowPlan.make(track: distant, at: 1.01) == .fullSource)
    }
}
```

- [ ] **Step 2: Run the new tests and verify they fail because the symbols do not exist**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' \
  -only-testing:kpopTests/PortraitFollowGeometryTests test
```

Expected: compilation failure mentioning `PortraitFollowPlan` is not in scope.

- [ ] **Step 3: Implement the pure geometry contract**

```swift
import CoreGraphics
import Foundation

nonisolated struct NormalizedRect: Equatable, Sendable {
    let minX: Double
    let minY: Double
    let width: Double
    let height: Double

    var maxX: Double { minX + width }
    var maxY: Double { minY + height }
    var centerX: Double { minX + width / 2 }
    var centerY: Double { minY + height / 2 }

    func contains(x: Double, y: Double) -> Bool {
        x >= minX && x <= maxX && y >= minY && y <= maxY
    }
}

nonisolated enum PortraitFollowFrame: Equatable, Sendable {
    case fullSource
    case tracking(NormalizedRect)

    var centerX: Double { crop?.centerX ?? 0.5 }
    var crop: NormalizedRect? {
        if case .tracking(let value) = self { return value }
        return nil
    }
}

nonisolated enum PortraitFollowPlan {
    static let targetAspect = 9.0 / 16.0
    static let minimumConfidence = 0.55
    static let maximumGapSeconds = 1.0

    static func make(track: [AnalysisSpotlightKeyframe], at time: Double) -> PortraitFollowFrame {
        guard let keyframe = interpolated(track: track, at: time), keyframe.confidence >= minimumConfidence else {
            return .fullSource
        }
        return crop(for: keyframe).map(PortraitFollowFrame.tracking) ?? .fullSource
    }
}
```

Implement `interpolated(track:at:)` by sorting finite keyframes by `timeSeconds`, rejecting timestamps more than `maximumGapSeconds` from both neighboring frames, and linearly interpolating each box field and confidence. Implement `crop(for:)` by expanding the box by `20%` horizontally and `16%` vertically, computing the smallest 9:16 rectangle that contains that expanded box, and returning `nil` if it cannot remain inside `[0,1] x [0,1]`. Clamp only the origin after a valid crop size exists; do not silently shrink a crop that would lose a padded body part.

- [ ] **Step 4: Add full-body pose retention coverage**

In `kpopTests/AnalysisPackageTests.swift`, add the assertion below to the existing successful package decode test:

```swift
#expect(package.poseTrack.allSatisfy { frame in
    frame.keypoints.contains(where: { $0.name == "left_wrist" })
        && frame.keypoints.contains(where: { $0.name == "right_wrist" })
        && frame.keypoints.contains(where: { $0.name == "left_ankle" })
        && frame.keypoints.contains(where: { $0.name == "right_ankle" })
})
```

If the fixture uses COCO numeric names, update the fixture to use the worker's stable full-body keypoint names before adding the assertion; do not remove keypoints from the package decoder.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' \
  -only-testing:kpopTests/PortraitFollowGeometryTests \
  -only-testing:kpopTests/AnalysisPackageTests test
git add kpop/Domain/Practice/PortraitFollowGeometry.swift kpopTests/PortraitFollowGeometryTests.swift kpopTests/AnalysisPackageTests.swift
git commit -m 'feat: add portrait follow geometry'
```

Expected: all selected tests pass on iOS 26.5.

## Task 2: AVFoundation Composition and 9:16 Player

**Files:**
- Create: `kpop/Domain/Practice/PortraitFollowComposition.swift`
- Create: `kpop/Views/PortraitFollowPlayerView.swift`
- Create: `kpopTests/PortraitFollowCompositionTests.swift`

**Interfaces:**
- Consumes: `PortraitFollowFrame`, `NormalizedRect`, `AVAsset`, `AVAssetTrack`.
- Produces: `PortraitFollowCompositionBuilder.makeItem(asset:track:) async throws -> AVPlayerItem`.
- Produces: `PortraitFollowPlayerView(player:isMirrored:)` for PracticeStageView.

- [ ] **Step 1: Write failing composition-plan tests**

```swift
import AVFoundation
import CoreVideo
import Testing
@testable import kpop

private enum TestVideoAsset {
    static func make(size: CGSize, duration: Double) async throws -> AVURLAsset {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("mov")
        let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let input = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: Int(size.width),
                AVVideoHeightKey: Int(size.height)
            ]
        )
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        )
        writer.add(input)
        #expect(writer.startWriting())
        writer.startSession(atSourceTime: .zero)
        let frameCount = Int(duration * 30)
        for index in 0..<frameCount where input.isReadyForMoreMediaData {
            var buffer: CVPixelBuffer?
            CVPixelBufferCreate(kCFAllocatorDefault, Int(size.width), Int(size.height), kCVPixelFormatType_32BGRA, nil, &buffer)
            adaptor.append(try #require(buffer), withPresentationTime: CMTime(value: Int64(index), timescale: 30))
        }
        input.markAsFinished()
        await writer.finishWriting()
        guard writer.status == .completed else { throw writer.error ?? CocoaError(.fileWriteUnknown) }
        return AVURLAsset(url: url)
    }
}

@Test
func trackingPlanProducesNineBySixteenRenderSizeAndCropRamp() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(
        asset: asset,
        frames: [
            .tracking(NormalizedRect(minX: 0.2, minY: 0, width: 0.5625, height: 1)),
            .tracking(NormalizedRect(minX: 0.25, minY: 0, width: 0.5625, height: 1))
        ]
    )

    let composition = try #require(item.videoComposition)
    #expect(abs(composition.renderSize.width / composition.renderSize.height - 9.0 / 16.0) < 0.001)
    #expect(composition.instructions.isEmpty == false)
}

@Test
func fullSourcePlanUsesAspectFitTransformInsteadOfDroppingPlayback() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(asset: asset, frames: [.fullSource])
    #expect(item.asset === asset)
    #expect(item.videoComposition != nil)
}
```

- [ ] **Step 2: Run the test and verify it fails because the builder does not exist**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' \
  -only-testing:kpopTests/PortraitFollowCompositionTests test
```

Expected: compilation failure mentioning `PortraitFollowCompositionBuilder` is not in scope.

- [ ] **Step 3: Implement AVFoundation render instructions**

```swift
import AVFoundation
import CoreGraphics

enum PortraitFollowCompositionBuilder {
    static func makeItem(asset: AVAsset, frames: [PortraitFollowFrame]) async throws -> AVPlayerItem {
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard let track = tracks.first else { return AVPlayerItem(asset: asset) }
        let duration = try await asset.load(.duration)
        let naturalSize = try await track.load(.naturalSize)
        let renderSize = portraitRenderSize(for: naturalSize)

        let composition = AVMutableVideoComposition()
        composition.renderSize = renderSize
        composition.frameDuration = CMTime(value: 1, timescale: 30)
        composition.instructions = makeInstructions(
            track: track,
            duration: duration,
            sourceSize: naturalSize,
            renderSize: renderSize,
            frames: frames
        )

        let item = AVPlayerItem(asset: asset)
        item.videoComposition = composition
        return item
    }
}
```

`makeInstructions` must use `AVMutableVideoCompositionLayerInstruction.setCropRectangleRamp(fromStartCropRectangle:toEndCropRectangle:timeRange:)` for each contiguous tracking span. It must pair each crop ramp with a transform ramp that maps its source crop to the fixed portrait render size. For `.fullSource`, use the complete natural source rectangle and an aspect-fit transform centered inside the 9:16 render size, leaving black bars rather than cutting an untracked dancer. Apply the track's preferred transform before crop placement so rotated source media is presented upright. Use even positive render dimensions and return the uncomposed `AVPlayerItem(asset:)` if no video track exists.

- [ ] **Step 4: Implement the layer-backed player view**

```swift
import AVFoundation
import SwiftUI

struct PortraitFollowPlayerView: UIViewRepresentable {
    let player: AVPlayer
    let isMirrored: Bool

    func makeUIView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.player = player
        view.isMirrored = isMirrored
        return view
    }

    func updateUIView(_ view: PlayerLayerView, context: Context) {
        view.player = player
        view.isMirrored = isMirrored
    }
}

final class PlayerLayerView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var player: AVPlayer? { didSet { playerLayer.player = player } }
    var isMirrored = false { didSet { playerLayer.setAffineTransform(isMirrored ? CGAffineTransform(scaleX: -1, y: 1) : .identity) } }
    private var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }

    override init(frame: CGRect) {
        super.init(frame: frame)
        playerLayer.videoGravity = .resizeAspect
        backgroundColor = .black
    }

    required init?(coder: NSCoder) { nil }
}
```

Keep `videoGravity` at `.resizeAspect`: the video composition already yields portrait tracking output, and fallback output intentionally contains letterboxing.

- [ ] **Step 5: Run focused tests, build, and commit**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' \
  -only-testing:kpopTests/PortraitFollowCompositionTests test
xcodebuild -project kpop.xcodeproj -scheme kpop -configuration Debug \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' build
git add kpop/Domain/Practice/PortraitFollowComposition.swift kpop/Views/PortraitFollowPlayerView.swift kpopTests/PortraitFollowCompositionTests.swift
git commit -m 'feat: render portrait follow composition'
```

Expected: selected composition tests and the iOS 26.5 Debug build pass.

## Task 3: Practice Screen and Overlay Integration

**Files:**
- Modify: `kpop/Views/PracticePlaceholderView.swift`
- Modify: `kpop/Views/PracticePlayerView.swift`
- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**
- Consumes: `PortraitFollowPlan`, `PortraitFollowCompositionBuilder`, `PortraitFollowPlayerView`, `AnalysisPackage`.
- Produces: a 9:16 `PracticeStageView` with tracking video, aligned skeleton/box overlays, and visible fallback state.

- [ ] **Step 1: Write failing presentation-state tests**

Add a pure helper to `PracticePlaceholderView.swift` or `PortraitFollowGeometry.swift` and test it without UI automation:

```swift
@Test
func trackingPresentationShowsFallbackOnlyWhenNoReliableCropExists() {
    #expect(PracticeFollowPresentation(frame: .tracking(.init(minX: 0.2, minY: 0, width: 0.5625, height: 1))).status == .tracking)
    #expect(PracticeFollowPresentation(frame: .fullSource).status == .fullFrameFallback)
}
```

Run the target test and confirm it fails before adding `PracticeFollowPresentation`.

- [ ] **Step 2: Integrate asynchronous player preparation**

Replace the direct `AVPlayer(url:)` setup in `PracticeView.preparePlayer()` with an async task that loads `AVURLAsset`, derives the ordered `PortraitFollowFrame` sequence from `analysisPackage?.spotlightTrack`, and assigns the `AVPlayer` created from `PortraitFollowCompositionBuilder.makeItem`. When the package is absent, invalid, or the builder throws, create `AVPlayer(url:)` and set presentation status to `.fullFrameFallback`; never block playback or delete the package.

Use this exact state type:

```swift
enum PracticeFollowStatus: Equatable {
    case tracking
    case fullFrameFallback
    case unavailable
}
```

The player must be recreated when either `project.sourceVideoPath` or `project.analysisPackageRelativePath` changes. Preserve the existing periodic observer, speed binding, loop behavior, and cleanup sequence.

- [ ] **Step 3: Render a portrait stage and aligned overlay**

Change `PracticeStageView` to use `PortraitFollowPlayerView` and enforce:

```swift
.aspectRatio(9.0 / 16.0, contentMode: .fit)
.frame(maxWidth: .infinity)
```

Remove its fixed `.frame(height: 300)`. Update `PracticeAnalysisOverlay` to project each normalized spotlight rectangle and pose keypoint through the active `PortraitFollowFrame` before drawing. For `.fullSource`, project into the centered aspect-fit source rectangle; for `.tracking(crop)`, map `(x - crop.minX) / crop.width` and `(y - crop.minY) / crop.height`. Apply the same final horizontal mirror transform to `PortraitFollowPlayerView` and the overlay. Show a compact status badge: `全身跟随` for tracking, `完整画面` for fallback, and `跟随数据不可用` when no result package is loaded.

- [ ] **Step 4: Run full automated gates on iOS 26.5**

Run:

```bash
./scripts/verify-backend.sh
xcodebuild -project kpop.xcodeproj -scheme kpop \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' test
xcodebuild -project kpop.xcodeproj -scheme kpop -configuration Debug \
  -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' build
```

Expected: backend test suite remains green; iOS test/build results are recorded exactly. If CoreSimulator terminates before test execution, record it as a simulator infrastructure failure and still require the Debug build to succeed before continuing.

- [ ] **Step 5: Run the manual local-AI acceptance flow**

1. Start `./scripts/run-local-ai-demo.sh --port 8000`.
2. Launch the Debug app with the local pairing environment on iPhone 17 Pro Max iOS 26.5.
3. Import the 82MAJOR sample, complete upload, select one real candidate, and wait for `resultReady`.
4. In practice, confirm the video output is 9:16, the selected dancer stays inside the padded crop, skeleton/box stay attached during movement, and mirror reverses both together.
5. Scrub to a low-confidence or absent-track interval and confirm a non-blocking complete-frame fallback.
6. Test `0.5x`, `0.75x`, `1x`, loop, app background/foreground, then terminate and relaunch to confirm the stored package still supports offline practice.

Record elapsed analysis time, manual observations, failures, and the exact simulator OS in `docs/PROJECT_STATUS.md`.

- [ ] **Step 6: Update status, commit, and prepare review**

Update `docs/PROJECT_STATUS.md` only with verified results: changed iOS files, no backend/schema changes, iOS 26.5 test/build output, manual acceptance result, simulator decoder limitations, and any unresolved issue. Then run:

```bash
git add kpop/Views/PracticePlaceholderView.swift kpop/Views/PracticePlayerView.swift docs/PROJECT_STATUS.md
git commit -m 'feat: add portrait practice follow mode'
git status --short
```

Do not stage user-owned changes in `kpop.xcodeproj`, its shared schemes, or `Kpop-Dance-APP/`.

## Plan Self-Review

- Spec coverage: Tasks 1-3 cover full-body data preservation, 9:16 layout, safe body-first crop, smooth interpolation, confidence/gap fallback, aligned overlay/mirror, iOS 26.5-only verification, and no backend/schema/model changes.
- Placeholder scan: no deferred behavior or unspecified edge handling remains; confidence, gap, padding, crop ratio, fallback, device UDID, commands, and commit boundaries are explicit.
- Type consistency: `NormalizedRect`, `PortraitFollowFrame`, `PortraitFollowPlan`, `PortraitFollowCompositionBuilder`, `PortraitFollowPlayerView`, and `PracticeFollowStatus` are defined before their consuming tasks.
