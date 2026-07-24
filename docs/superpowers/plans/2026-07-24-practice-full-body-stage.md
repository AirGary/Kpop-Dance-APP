# Practice Full-Body Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crowded practice screen with the approved B2 full-body locked stage while preserving existing local playback and analysis-package behavior.

**Architecture:** Keep follow-crop selection and skeleton topology as pure, testable domain helpers. Move the visual stage and its compact controls out of `PracticePlaceholderView.swift`; the page owns bindings and persistence while the stage consumes immutable presentation values and callbacks.

**Tech Stack:** SwiftUI, AVFoundation, Swift Testing, iOS 26.5 Simulator.

## Global Constraints

- Support iPhone 17 Pro Max on iOS 26.5; no iOS 27-only API.
- Do not change backend, model, Analysis Package schema, cloud resources, or local file ownership.
- Keep video, candidate images, screenshots, and absolute sample paths out of Git.
- Preserve speed, mirror, loop, seek, local-media recovery, and player-observer cleanup behavior.
- The video stage occupies approximately 84% of the initial scroll viewport; no yellow target rectangle is rendered.
- Use `kpopTests` as the test target; do not rely on a file-level Swift Testing filter.

---

### Task 1: Stable full-body follow frame

**Files:**
- Modify: `kpop/Domain/Practice/PortraitFollowGeometry.swift:159-264`
- Modify: `kpopTests/PortraitFollowGeometryTests.swift:1-157`

**Interfaces:**
- Consumes: `AnalysisSpotlightKeyframe`, `PortraitFollowFrame`, `NormalizedRect`.
- Produces: `PortraitFollowPlan.make(track:at:) -> PortraitFollowFrame` that holds the last valid full-body crop during a bounded unreliable interval and otherwise returns `.fullSource`.

- [ ] **Step 1: Write the failing hold-last-frame tests**

```swift
@Test
func shortLowConfidenceGapHoldsThePreviousFullBodyCrop() throws {
    let track = [
        AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.38, y: 0.08, width: 0.22, height: 0.82, confidence: 0.92),
        AnalysisSpotlightKeyframe(timeSeconds: 0.5, x: 0.40, y: 0.08, width: 0.22, height: 0.82, confidence: 0.10)
    ]
    let previous = try #require(PortraitFollowPlan.make(track: track, at: 0).crop)
    let held = try #require(PortraitFollowPlan.make(track: track, at: 0.5).crop)
    #expect(held == previous)
}

@Test
func longLowConfidenceGapFallsBackToFullSource() {
    let track = [AnalysisSpotlightKeyframe(timeSeconds: 0, x: 0.38, y: 0.08, width: 0.22, height: 0.82, confidence: 0.92)]
    #expect(PortraitFollowPlan.make(track: track, at: 1.01) == .fullSource)
}
```

- [ ] **Step 2: Run the full iOS test target to observe the first test fail**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' test`

Expected: the new short-gap test fails because the current implementation returns `.fullSource` for the low-confidence keyframe.

- [ ] **Step 3: Add a bounded prior-valid-keyframe lookup**

```swift
private static func heldFrame(
    in track: [AnalysisSpotlightKeyframe],
    at time: Double
) -> PortraitFollowFrame? {
    guard let prior = track
        .filter({ $0.timeSeconds <= time && time - $0.timeSeconds <= maximumGapSeconds })
        .sorted(by: { $0.timeSeconds > $1.timeSeconds })
        .first(where: { $0.confidence >= minimumConfidence && isNormalized($0) }),
          let crop = crop(for: prior) else { return nil }
    return .tracking(crop)
}
```

Call `heldFrame(in:at:)` only after interpolation cannot produce a reliable crop; retain `.fullSource` when no eligible previous frame exists.

- [ ] **Step 4: Run the full iOS test target and inspect the new tests**

Run the command from Step 2. Expected: 0 failures; existing invalid-frame gap tests retain their asserted fallback behavior.

- [ ] **Step 5: Commit the isolated geometry change**

```bash
git add kpop/Domain/Practice/PortraitFollowGeometry.swift kpopTests/PortraitFollowGeometryTests.swift
git commit -m "feat: hold stable full body follow frame"
```

### Task 2: Anatomical skeleton projection

**Files:**
- Create: `kpop/Domain/Practice/PracticeSkeleton.swift`
- Modify: `kpop/Views/PracticePlaceholderView.swift:602-655`
- Create: `kpopTests/PracticeSkeletonTests.swift`

**Interfaces:**
- Consumes: projected `CGPoint` values indexed by the Analysis Package keypoint order.
- Produces: `PracticeSkeleton.segments(points:) -> [(CGPoint, CGPoint)]`, containing only anatomical pairs with two valid points.

- [ ] **Step 1: Write failing topology tests**

```swift
@Test
func skeletonUsesOnlyDefinedAnatomicalPairs() {
    let points = (0..<17).map { CGPoint(x: CGFloat($0), y: CGFloat($0)) }
    let segments = PracticeSkeleton.segments(points: points)
    #expect(segments.contains { $0.0 == points[5] && $0.1 == points[7] })
    #expect(!segments.contains { $0.0 == points[0] && $0.1 == points[1] })
}
```

- [ ] **Step 2: Run `kpopTests` and verify the new test fails because `PracticeSkeleton` is absent.**

- [ ] **Step 3: Implement the fixed pair list and discard incomplete pairs**

```swift
nonisolated enum PracticeSkeleton {
    static let pairs = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
    static func segments(points: [CGPoint?]) -> [(CGPoint, CGPoint)] {
        pairs.compactMap { first, second in
            guard points.indices.contains(first), points.indices.contains(second),
                  let start = points[first], let end = points[second] else { return nil }
            return (start, end)
        }
    }
}
```

Replace the `zip(points, points.dropFirst())` loop with `PracticeSkeleton.segments(points:)`, and use cyan at low opacity with 2pt lines; remove the yellow spotlight rectangle rendering entirely.

- [ ] **Step 4: Run `kpopTests` and confirm topology plus existing overlay projections pass.**

- [ ] **Step 5: Commit**

```bash
git add kpop/Domain/Practice/PracticeSkeleton.swift kpop/Views/PracticePlaceholderView.swift kpopTests/PracticeSkeletonTests.swift
git commit -m "feat: render anatomical practice skeleton"
```

### Task 3: B2 immersive practice-stage layout

**Files:**
- Create: `kpop/Views/PracticeStageView.swift`
- Modify: `kpop/Views/PracticePlaceholderView.swift:1-655`
- Modify: `kpopTests/PortraitFollowGeometryTests.swift`

**Interfaces:**
- Consumes: `AVPlayer`, `PracticeFollowStatus`, `AnalysisPackage`, `PortraitFollowFrame`, bindings for mirror/loop/skeleton/rate and playback callbacks.
- Produces: `PracticeStageView` with a 9:16 stage, status capsule, 44pt-hit-target compact bar, and `NextMoveCard`.

- [ ] **Step 1: Add an accessibility regression test for each compact action label**

Create a SwiftUI view inspection-free contract test that exposes the exact strings `播放练习`, `镜像模式`, `片段循环`, `目标骨架`, and the selected speed title through `accessibilityLabel` values in the stage helper. Run it and observe the missing stage symbols fail.

- [ ] **Step 2: Extract the private stage, overlay, control-chip and toggle-card types into `PracticeStageView.swift`.**

The new stage must have this public initializer shape inside the module:

```swift
PracticeStageView(
    player: player,
    title: project.title,
    dancerName: project.selectedDancerName,
    currentTime: currentTime,
    totalDuration: safeDuration,
    followStatus: activeFollowStatus,
    analysisPackage: analysisPackage,
    followFrame: activeFollowFrame,
    sourceAspectRatio: sourceAspectRatio,
    isMirrored: project.mirrorEnabled,
    isPlaying: isPlaying,
    playbackRate: project.playbackRate,
    loopEnabled: $loopEnabled,
    showSkeleton: $showSkeleton,
    onTogglePlayback: togglePlayback,
    onSeek: seek
)
```

Render `.tracking` as `舞者 N · 全身锁定`; render `.fullFrameFallback` as `完整画面`; render `.unavailable` as `跟随数据不可用`. Do not draw a spotlight rectangle in any state. Default `showSkeleton` to `false`.

- [ ] **Step 3: Replace the top `ScrollView` section with the extracted stage and a single next-action card.**

Place verbose speed picker, timeline list and formation guidance below the initial viewport. Preserve all existing bindings, disabled behavior for missing local video, `onDisappear` cleanup and end-of-video looping.

- [ ] **Step 4: Run `kpopTests` and a Debug build.**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' test` and then `xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,id=DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA' build`.

Expected: both commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add kpop/Views/PracticePlaceholderView.swift kpop/Views/PracticeStageView.swift kpopTests/PortraitFollowGeometryTests.swift
git commit -m "feat: redesign immersive practice stage"
```

### Task 4: Simulator visual and recovery validation

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**
- Consumes: complete Tasks 1-3 build and the iPhone 17 Pro Max Simulator UDID.
- Produces: evidence distinguishing automatic verification, Simulator visual smoke, and unexecuted real-media checks.

- [ ] **Step 1: Start the iPhone 17 Pro Max iOS 26.5 Simulator and install the Debug app.**

Run `xcrun simctl bootstatus DF1DB4C3-C579-46A7-8BEB-D1B01D99A7DA -b`, then install the built `.app` and launch bundle identifier `fausyusgarygary.kpop.dev`.

- [ ] **Step 2: Verify the missing-media recovery page and an imported local sample separately.**

For missing media, confirm controls are disabled and recovery copy remains readable. For an explicitly user-provided local sample, confirm no yellow rectangle, full-body status, compact bar hit targets, mirror, speed, loop, skeleton toggle and offline restart. Do not claim the sample check if no local media is available.

- [ ] **Step 3: Capture only non-sensitive screenshots outside Git and update `docs/PROJECT_STATUS.md`.**

Record commands, date, simulator, pass/fail count, unreadable-result-bundle limitation if it recurs, and all unexecuted real-media checks.

- [ ] **Step 4: Run final verification and commit documentation.**

Run the full `kpopTests` command from Task 3 Step 4, `git diff --check`, and `git status --short`. Commit only the updated status document after results are recorded.

```bash
git add docs/PROJECT_STATUS.md
git commit -m "docs: record full body stage validation"
```

## Plan Self-Review

- Spec coverage: Task 1 covers stable full-body lock and fallback; Task 2 removes the detection rectangle and fixes bone topology; Task 3 covers B2 layout, compact controls, state copy and preserved behavior; Task 4 covers Simulator evidence and documented limitations.
- Placeholder scan: the plan contains no deferred implementation markers; every code change includes exact files, an interface and a verification command.
- Type consistency: all tasks use existing `PortraitFollowFrame`, `PracticeFollowStatus`, `AnalysisPackage`, `AVPlayer`, `PlaybackRate` and `PracticeOverlayProjection`; the only new public pure helper is `PracticeSkeleton.segments(points:)`.
