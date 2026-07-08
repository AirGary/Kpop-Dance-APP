# Task 1 Report: Extend Project Persistence For Local Video Playback

## Scope

- Modified `kpop/Models/DanceProject.swift`
- Created `kpop/Models/ImportedVideo.swift`
- Preserved existing navigation flow and all current model behavior outside the requested persistence additions

## What Changed

### `DanceProject`

Added the persistence fields required by later import and practice tasks:

- `sourceVideoPath: String?`
- `videoDuration: Double`

Extended the existing initializer with:

- `sourceVideoPath: String? = nil`
- `videoDuration: Double = 0`

These additions are backward-compatible with the current call site in `ImportPlaceholderView` because both new parameters are defaulted.

### `ImportedVideo.swift`

Added:

- `ImportedVideo`
  - `fileURL: URL`
  - `displayName: String`
  - `duration: Double`
- `ImportedVideoStore.copyVideo(from:) async throws -> ImportedVideo`

Implementation details:

- Copies the selected source file into `Application Support/ImportedVideos`
- Preserves the original file extension, defaulting to `mov` when none exists
- Uses a UUID-based filename to avoid collisions
- Loads duration from `AVURLAsset`
- Normalizes non-finite durations to `0`
- Uses the original source filename (without extension) as `displayName`

## TDD / Build-First Workflow

Because this repository does not have an XCTest target, I followed the task brief's compile-contract approach as closely as the local environment allowed.

### Red

I first added a compile-contract reference in `ImportedVideo.swift`:

```swift
let project = DanceProject(
    title: "Demo",
    sourceVideoPath: "/tmp/demo.mov",
    videoDuration: 92.0
)
_ = project.sourceVideoPath
_ = project.videoDuration

let store = ImportedVideoStore()
```

Then I ran:

```bash
xcrun swiftc -typecheck 'kpop/Models/DanceProject.swift' 'kpop/Models/ImportedVideo.swift'
```

Observed expected failure before implementation:

```text
kpop/Models/DanceProject.swift:148:28: error: extra argument 'videoDuration' in call
```

This confirmed the compile contract did not exist yet.

### Green

After implementing the new stored properties and import helper, I re-ran:

```bash
xcrun swiftc -typecheck 'kpop/Models/DanceProject.swift' 'kpop/Models/ImportedVideo.swift'
```

Observed success with exit code `0`.

## Requested `xcodebuild` Verification

I also ran the task brief's requested build command before and after implementation:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build
```

Both runs were blocked before source compilation by the local Xcode environment, not by project code:

```text
xcodebuild: error: Unable to find a device matching the provided destination specifier:
{ platform:iOS Simulator, OS:latest, name:iPhone 16 }
```

Additional environment evidence:

- `xcrun simctl list devices available` returned no available simulators
- `xcodebuild -showdestinations` reported only ineligible iOS destinations because iOS 26.5 is not installed locally

So the code-level compile verification for this task is currently represented by the successful `swiftc -typecheck` run on the two owned model files.

## Self-Review

- Kept `DanceProject` changes minimal and backward-compatible
- Avoided altering route flow, views, or unrelated model behavior
- Kept the compile-contract helper private to the new `ImportedVideo.swift` file so it does not expand the production API surface
- Confirmed no whitespace or patch-format issues with `git diff --check`

## Remaining Concern

The brief's exact simulator build could not be completed on this machine until an iOS Simulator runtime is installed and a matching destination exists. Once that environment issue is resolved, re-running the requested `xcodebuild` command should be the next verification step.

## Review Fix Follow-Up

Addressed the three required findings with minimal changes limited to the owned Task 1 files.

### 1. Migration-safe default for `videoDuration`

Updated `DanceProject.videoDuration` from a bare non-optional property to a property-level defaulted field:

```swift
var videoDuration: Double = 0
```

This keeps the field non-optional for downstream consumers while giving SwiftData an evident default value at the model property level, which is safer for existing persisted stores than relying only on the initializer default.

### 2. Cleanup copied file if metadata loading fails

Wrapped `AVURLAsset` metadata loading in `do/catch` and remove the copied file before rethrowing:

```swift
do {
    ...
} catch {
    try? FileManager.default.removeItem(at: fileURL)
    throw error
}
```

This prevents orphaned imported files when duration loading fails after the copy succeeds.

### 3. Removed compile-contract helper from production source

Deleted the `persistenceCompileContract` helper entirely from `ImportedVideo.swift` so no compile-target-only helper remains in shipped code.

## Follow-Up Verification

Focused compile verification after the fixes:

```bash
xcrun swiftc -typecheck 'kpop/Models/DanceProject.swift' 'kpop/Models/ImportedVideo.swift'
```

Observed success with exit code `0`.

Focused source checks covering the reviewed concerns:

```bash
rg -n "persistenceCompileContract|removeItem\\(at: fileURL\\)|videoDuration: Double = 0" \
  'kpop/Models/DanceProject.swift' \
  'kpop/Models/ImportedVideo.swift'
```

Observed:

- `videoDuration: Double = 0` present in `DanceProject`
- cleanup removal present in `ImportedVideoStore`
- no `persistenceCompileContract` symbol remains

Formatting verification:

```bash
git diff --check -- 'kpop/Models/DanceProject.swift' 'kpop/Models/ImportedVideo.swift'
```

Observed success with no diff-check issues.

Requested simulator build re-run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build
```

Still blocked by local simulator availability rather than source code:

```text
xcodebuild: error: Unable to find a device matching the provided destination specifier:
{ platform:iOS Simulator, OS:latest, name:iPhone 16 }
```
