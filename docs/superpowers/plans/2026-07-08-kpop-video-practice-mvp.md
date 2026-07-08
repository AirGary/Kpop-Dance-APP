# K-pop Video Practice MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable iOS MVP where the user imports a real local dance video, creates a project, and reaches a practice screen that plays the actual video with seek, speed, mirror, and node jump controls.

**Architecture:** Keep the existing SwiftUI navigation flow and SwiftData project model, but upgrade persistence so each project stores a local copied video path and optional duration metadata. Add a focused AVPlayer-backed practice surface so playback state is isolated from the rest of the screen while the existing analysis and dancer-pick pages remain lightweight transition steps.

**Tech Stack:** SwiftUI, SwiftData, PhotosUI, AVFoundation, Xcode/iOS Simulator

## Global Constraints

- Keep the app iOS-only and preserve the existing `Home -> Import -> Analysis -> Dancer Pick -> Practice` navigation flow.
- Treat real video playback as the priority; analysis and timeline nodes remain lightweight demo behavior for this MVP.
- Do not mutate the original imported media; copy user-selected videos into app-managed local storage.
- Mirror mode must affect only display, never the stored file.
- Support `0.5x`, `0.75x`, and `1x` playback rates on the practice screen.
- The repository currently has no dedicated XCTest target, so verification must rely on targeted builds and simulator/manual checks unless a small test target is added intentionally.

---

### Task 1: Extend Project Persistence For Local Video Playback

**Files:**
- Modify: `kpop/Models/DanceProject.swift`
- Create: `kpop/Models/ImportedVideo.swift`

**Interfaces:**
- Consumes: Existing `DanceProject` SwiftData model and current route flow.
- Produces: `DanceProject.sourceVideoPath: String?`, `DanceProject.videoDuration: Double`, and `ImportedVideoStore.copyVideo(from:) async throws -> ImportedVideo`.

- [ ] **Step 1: Write the failing persistence-oriented compile target**

Document the intended compile contract before implementation:

```swift
// Expected additions used by later tasks
let project = DanceProject(title: "Demo", sourceVideoPath: "/tmp/demo.mov", videoDuration: 92.0)
_ = project.sourceVideoPath
_ = project.videoDuration

let store = ImportedVideoStore()
// copyVideo(from:) must return an ImportedVideo with local file URL, display name, and duration
```

- [ ] **Step 2: Run build to verify the contract does not exist yet**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: FAIL with missing `sourceVideoPath`, `videoDuration`, and `ImportedVideoStore` symbols.

- [ ] **Step 3: Write the minimal persistence implementation**

Add a focused import helper:

```swift
import Foundation
import AVFoundation

struct ImportedVideo {
    let fileURL: URL
    let displayName: String
    let duration: Double
}

struct ImportedVideoStore {
    func copyVideo(from sourceURL: URL) async throws -> ImportedVideo {
        let directory = try storageDirectory()
        let ext = sourceURL.pathExtension.isEmpty ? "mov" : sourceURL.pathExtension
        let fileURL = directory.appendingPathComponent("\(UUID().uuidString).\(ext)")

        if FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }

        try FileManager.default.copyItem(at: sourceURL, to: fileURL)

        let asset = AVURLAsset(url: fileURL)
        let duration = try await asset.load(.duration).seconds
        let name = sourceURL.deletingPathExtension().lastPathComponent

        return ImportedVideo(fileURL: fileURL, displayName: name, duration: duration.isFinite ? duration : 0)
    }

    private func storageDirectory() throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent("ImportedVideos", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }
}
```

- [ ] **Step 4: Update `DanceProject` to store video path and duration**

Minimal model shape:

```swift
@Model
final class DanceProject {
    // existing properties...
    var sourceVideoPath: String?
    var videoDuration: Double

    init(
        id: UUID = UUID(),
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        title: String,
        sourceVideoName: String = "本地视频",
        sourceVideoPath: String? = nil,
        videoDuration: Double = 0,
        selectedDancerName: String? = nil,
        mirrorEnabled: Bool = false,
        defaultPlaybackRate: Double = 1.0,
        phase: ProjectPhase = .created
    ) {
        self.sourceVideoPath = sourceVideoPath
        self.videoDuration = videoDuration
        // keep existing assignments
    }
}
```

- [ ] **Step 5: Run build to verify the persistence layer compiles**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kpop/Models/DanceProject.swift kpop/Models/ImportedVideo.swift
git commit -m "feat: persist imported video metadata"
```

### Task 2: Upgrade The Import Screen To Copy Real Videos And Create Valid Projects

**Files:**
- Modify: `kpop/Views/ImportPlaceholderView.swift`

**Interfaces:**
- Consumes: `ImportedVideoStore.copyVideo(from:) async throws -> ImportedVideo`, `DanceProject(sourceVideoPath:videoDuration:)`.
- Produces: Import UI state that copies a selected video, surfaces errors, and inserts a `DanceProject` with a valid local path.

- [ ] **Step 1: Write the failing import behavior target**

Document the intended screen behavior:

```swift
// ImportView needs state for:
// isImporting: Bool
// importErrorMessage: String?
// importedVideo: ImportedVideo?
//
// Creating a project must require importedVideo != nil
// and pass sourceVideoPath/videoDuration into DanceProject
```

- [ ] **Step 2: Run build to verify the screen contract is missing**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: FAIL after adding the references for import state until the screen is updated.

- [ ] **Step 3: Implement async import state and error handling**

Add state like:

```swift
@State private var importedVideo: ImportedVideo?
@State private var isImporting = false
@State private var importErrorMessage: String?
private let importedVideoStore = ImportedVideoStore()
```

Use `.task(id: selectedVideoItem)` or an async helper:

```swift
private func importSelectedVideo(_ item: PhotosPickerItem) async {
    isImporting = true
    importErrorMessage = nil

    do {
        guard let sourceURL = try await item.loadTransferable(type: URL.self) else {
            throw ImportError.unreadableSelection
        }
        let imported = try await importedVideoStore.copyVideo(from: sourceURL)
        importedVideo = imported
        sourceVideoName = imported.displayName
        if normalizedTitle.isEmpty {
            title = imported.displayName
        }
    } catch {
        importedVideo = nil
        importErrorMessage = "视频导入失败，请重新选择。"
    }

    isImporting = false
}
```

- [ ] **Step 4: Implement create-project gating and UI feedback**

Required behavior:

```swift
Button {
    guard let importedVideo else { return }
    let project = DanceProject(
        title: normalizedTitle,
        sourceVideoName: importedVideo.displayName,
        sourceVideoPath: importedVideo.fileURL.path,
        videoDuration: importedVideo.duration,
        phase: .analyzing
    )
    modelContext.insert(project)
    router.push(.analysis(projectId: project.id))
} label: {
    Label("创建并开始分析", systemImage: "waveform.path.ecg")
}
.disabled(normalizedTitle.isEmpty || importedVideo == nil || isImporting)
```

Also show:

```swift
if isImporting { ProgressView("正在导入视频...") }
if let importErrorMessage { Text(importErrorMessage).foregroundStyle(.red) }
if let importedVideo { Text("时长 \(formattedDuration(importedVideo.duration))") }
```

- [ ] **Step 5: Run build to verify the import flow compiles**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add kpop/Views/ImportPlaceholderView.swift
git commit -m "feat: import local practice videos"
```

### Task 3: Add A Focused AVPlayer Practice Surface

**Files:**
- Create: `kpop/Views/PracticePlayerView.swift`
- Modify: `kpop/Views/PracticePlaceholderView.swift`

**Interfaces:**
- Consumes: `DanceProject.sourceVideoPath`, `DanceProject.videoDuration`, `PlaybackRate`.
- Produces: `PracticePlayerView(player:isMirrored:)`, sync between slider, node taps, player time, and playback rate.

- [ ] **Step 1: Write the failing playback behavior target**

Document the intended compile contract:

```swift
let player = AVPlayer(url: URL(fileURLWithPath: "/tmp/demo.mov"))
let view = PracticePlayerView(player: player, isMirrored: false)
_ = view

// PracticeView must manage:
// player: AVPlayer?
// duration: Double
// isPlaying: Bool
// currentTime synced from periodic time observer
```

- [ ] **Step 2: Run build to verify the playback surface does not exist yet**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: FAIL with missing `PracticePlayerView` and playback state.

- [ ] **Step 3: Implement the minimal player surface**

Create a simple player wrapper:

```swift
import SwiftUI
import AVKit

struct PracticePlayerView: View {
    let player: AVPlayer
    let isMirrored: Bool

    var body: some View {
        VideoPlayer(player: player)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .scaleEffect(x: isMirrored ? -1 : 1, y: 1)
    }
}
```

- [ ] **Step 4: Replace the fake stage with real playback state**

`PracticeView` should:

```swift
@State private var player: AVPlayer?
@State private var duration: Double = 0
@State private var isPlaying = false
@State private var timeObserverToken: Any?
```

Load player on appear:

```swift
private func preparePlayer() {
    guard let path = project.sourceVideoPath else { return }
    let url = URL(fileURLWithPath: path)
    let player = AVPlayer(url: url)
    self.player = player
    duration = max(project.videoDuration, 1)
    addTimeObserver(to: player)
}
```

Support controls:

```swift
private func togglePlayback() {
    guard let player else { return }
    if isPlaying {
        player.pause()
    } else {
        player.play()
        player.rate = Float(project.playbackRate.rawValue)
    }
    isPlaying.toggle()
}

private func seek(to time: Double) {
    guard let player else { return }
    let target = CMTime(seconds: time, preferredTimescale: 600)
    player.seek(to: target)
}
```

Use `PracticePlayerView` when `player != nil`; otherwise show an unavailable card.

- [ ] **Step 5: Add node clamping and playback-safe slider range**

Required behavior:

```swift
private var safeDuration: Double { max(duration, 1) }

private var visibleTimelineNodes: [DanceTimelineNode] {
    DanceProject.sampleTimelineNodes.filter { $0.time <= safeDuration }
}
```

The slider range must use `0...safeDuration`, and node taps must call `seek(to:)`.

- [ ] **Step 6: Run build to verify playback compiles**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add kpop/Views/PracticePlayerView.swift kpop/Views/PracticePlaceholderView.swift
git commit -m "feat: add real practice video playback"
```

### Task 4: Polish MVP Controls And Verify In Simulator

**Files:**
- Modify: `kpop/Views/PracticePlaceholderView.swift`
- Modify: `kpop/Views/ImportPlaceholderView.swift`

**Interfaces:**
- Consumes: Working import and playback features from Tasks 1-3.
- Produces: Better MVP UI feedback and a verified demo path for manual preview.

- [ ] **Step 1: Add missing control polish**

Required UI additions:

```swift
// Practice screen
// - primary play/pause button
// - current time and total duration labels
// - disabled controls when player == nil
// - "视频不可用" fallback card when file missing
//
// Import screen
// - imported filename summary
// - duration summary
// - import progress copy
```

- [ ] **Step 2: Run build to verify the polished UI compiles**

Run: `xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build`
Expected: PASS

- [ ] **Step 3: Run simulator verification**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build
```

Then manually verify in Simulator:
- Select a real local video from Photos.
- Create a project and continue to practice.
- Confirm the video plays.
- Confirm `0.5x`, `0.75x`, and `1x` change playback speed.
- Confirm mirror mode flips the display only.
- Confirm dragging the slider seeks.
- Confirm tapping a node jumps near the expected timestamp.

- [ ] **Step 4: Commit**

```bash
git add kpop/Views/PracticePlaceholderView.swift kpop/Views/ImportPlaceholderView.swift
git commit -m "feat: polish practice MVP controls"
```
