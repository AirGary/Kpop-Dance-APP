# Task 3 Report: Add A Focused AVPlayer Practice Surface

## Scope

- Created `/Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlayerView.swift`
- Modified `/Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlaceholderView.swift`
- Preserved the existing practice-page structure while replacing the fake stage with real local-video playback

## What Changed

### `PracticePlayerView`

- Added a focused AVKit wrapper:
  - `PracticePlayerView(player:isMirrored:)`
- Uses `VideoPlayer(player:)`
- Applies the required mirrored presentation with `scaleEffect(x:y:)`
- Clips the playback surface to the same rounded-card shape expected by the existing screen

### `PracticeView`

- Replaced placeholder practice-stage state with real playback state:
  - `player: AVPlayer?`
  - `duration: Double`
  - `isPlaying: Bool`
  - `timeObserverToken: Any?`
- Added `preparePlayer()` to:
  - read `project.sourceVideoPath`
  - validate that the copied local file exists
  - create an `AVPlayer`
  - seed `duration` from `project.videoDuration`
  - attach a periodic time observer
- Added `cleanupPlayer()` so the observer is removed and playback is paused on disappear or reload

### Playback synchronization

- Added `togglePlayback()` to drive play/pause against the real `AVPlayer`
- Added `seek(to:)` to keep slider changes and timeline node taps synced to player time
- Added a periodic time observer (`0.25s`) so `currentTime` tracks live playback
- Applied `project.playbackRate` to the active player when playback starts or when the segmented control changes during playback
- Added end-of-item handling:
  - if loop is enabled, seek to `0` and continue playing at the selected playback rate
  - otherwise stop playback and pin the visible time to the end

### Practice-surface UI updates

- Replaced the fake dancer-figure stage with the real `PracticePlayerView`
- Added a play/pause affordance directly on top of the video surface
- Added a matching play/pause control inside the existing “练习控制” card
- Added a `PracticeUnavailableView` fallback card when the local copied video cannot be found
- Disabled the slider and timeline node buttons when no playable local video is available so the screen no longer behaves like a fake practice surface

### Timeline and duration safety

- Added `safeDuration = max(duration, 1)`
- Clamped visible demo nodes to the real imported duration:
  - `DanceProject.sampleTimelineNodes.filter { $0.time <= safeDuration }`
- Updated the slider range to `0...safeDuration`
- Updated the trailing time label to show the real imported duration rather than the old fixed `1:00`

## Verification

### Requested simulator `xcodebuild` command

Command:

```bash
xcodebuild -project /Users/garysmac/Documents/kpop翻跳/kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build
```

Observed result:

```text
xcodebuild: error: Unable to find a device matching the provided destination specifier:
{ platform:iOS Simulator, OS:latest, name:iPhone 16 }
```

Environment evidence:

- `xcodebuild -showdestinations` reported only ineligible iOS destinations because `iOS 26.5` is not installed locally
- `xcrun simctl list devices available` returned only:

```text
== Devices ==
```

### Narrowest practical compile verification

Because there are no locally available simulator destinations, I ran focused Swift type checking against the changed files and their direct dependencies.

Command:

```bash
xcrun swiftc -typecheck -sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator26.5.sdk -target arm64-apple-ios18.0-simulator \
  /Users/garysmac/Documents/kpop翻跳/kpop/Router/Route.swift \
  /Users/garysmac/Documents/kpop翻跳/kpop/Router/AppRouter.swift \
  /Users/garysmac/Documents/kpop翻跳/kpop/Models/DanceProject.swift \
  /Users/garysmac/Documents/kpop翻跳/kpop/Views/AppUI.swift \
  /Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlayerView.swift \
  /Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlaceholderView.swift
```

Result:

- Passed with exit code `0`

### Source-format verification

Command:

```bash
git diff --check -- /Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlaceholderView.swift /Users/garysmac/Documents/kpop翻跳/kpop/Views/PracticePlayerView.swift
```

Result:

- Passed with no diff-check issues

## Self-Review

### Confirmed

- The practice screen now plays the copied local video instead of showing a fake dancer-stage placeholder
- Slider scrubbing, periodic player time updates, timeline node taps, and playback-rate changes all route through real `AVPlayer` state
- Demo timeline nodes remain demo-driven but are clamped to the imported video duration exactly as requested
- The view remains defensive when the file path is missing or the copied file is unavailable

### Residual concern

- Full scheme-level `xcodebuild` verification is still blocked by the local Xcode environment missing an installable iOS runtime / simulator destination, so the strongest code-level verification available in this workspace was successful focused Swift type checking rather than a complete app build
