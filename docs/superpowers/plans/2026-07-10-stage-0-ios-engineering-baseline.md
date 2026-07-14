# Stage 0 iOS Engineering Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current runnable SwiftUI demo into a reproducible iOS engineering baseline with preserved UI work, deterministic test launches, unit/UI test targets, three build environments, and one-command verification.

**Architecture:** Keep the current app behavior and SwiftData schema intact. Add only the minimum seams needed for deterministic tests: launch options and a model-container factory. Xcode remains the source of truth for app/test targets and build environments; cloud APIs and production domain refactors begin in later stages.

**Tech Stack:** Xcode 26.6, Swift 5 language mode with Swift 6.3.3 toolchain, SwiftUI, SwiftData, Swift Testing, XCTest/XCUITest, `xcodebuild`, zsh/bash.

## Global Constraints

- Minimum deployment target remains iOS 18.0.
- The first supported product device remains iPhone; iPad compatibility must not regress.
- Preserve the six existing uncommitted UI files and do not rewrite their visual design.
- Do not add Firebase, Google Cloud, AI models, networking, CloudKit, StoreKit, or new product behavior in Stage 0.
- Do not change the persisted `DanceProject` schema in Stage 0.
- Do not stage or commit `.superpowers/` browser-companion files.
- Every task ends with an independently verifiable build or test result and a focused commit.
- Use the simulator destination `platform=iOS Simulator,name=iPhone 17` for the documented local verification path.

---

## Target File Structure

```text
.gitignore
scripts/
  verify-ios.sh
kpop/
  App/
    AppLaunchOptions.swift
    ModelContainerFactory.swift
  kpopApp.swift
kpopTests/
  AppLaunchOptionsTests.swift
  ProjectModelTests.swift
kpopUITests/
  AppLaunchTests.swift
kpop.xcodeproj/
  project.pbxproj
  xcshareddata/xcschemes/
    kpop.xcscheme
    kpop-Staging.xcscheme
docs/development/
  ios-baseline.md
```

Responsibilities:

- `AppLaunchOptions.swift`: converts process arguments into deterministic launch behavior.
- `ModelContainerFactory.swift`: creates the normal disk-backed or UI-test in-memory SwiftData container.
- `kpopTests`: verifies stable model and launch behavior without launching a simulator UI.
- `kpopUITests`: verifies that a clean app reaches the Stage Lab home screen.
- `kpop-Staging.xcscheme`: creates a release-like TestFlight build that cannot overwrite production.
- `verify-ios.sh`: runs the exact Stage 0 build and test gates in a repeatable order.
- `ios-baseline.md`: teaches a beginner what each configuration and verification command means.

---

### Task 1: Preserve and Commit the Existing UI Baseline

**Files:**

- Verify only: `kpop/Views/AnalysisPlaceholderView.swift`
- Verify only: `kpop/Views/AppUI.swift`
- Verify only: `kpop/Views/DancerPickView.swift`
- Verify only: `kpop/Views/HomeView.swift`
- Verify only: `kpop/Views/ImportPlaceholderView.swift`
- Verify only: `kpop/Views/PracticePlaceholderView.swift`

**Interfaces:**

- Consumes: the existing UI changes already present in the working tree.
- Produces: one known-good commit that Stage 0 can safely build upon.

- [ ] **Step 1: Confirm the working tree scope**

Run:

```bash
git status --short
git diff --stat -- kpop/Views
```

Expected: exactly the six view files listed above are modified; `.superpowers/` may appear as untracked and must remain unstaged.

- [ ] **Step 2: Type-check the current app by building the simulator target**

Run:

```bash
xcodebuild \
  -project kpop.xcodeproj \
  -scheme kpop \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  build
```

Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 3: Review the exact staged scope**

Run:

```bash
git add \
  kpop/Views/AnalysisPlaceholderView.swift \
  kpop/Views/AppUI.swift \
  kpop/Views/DancerPickView.swift \
  kpop/Views/HomeView.swift \
  kpop/Views/ImportPlaceholderView.swift \
  kpop/Views/PracticePlaceholderView.swift
git diff --cached --check
git diff --cached --stat
```

Expected: only six view files are staged and `git diff --cached --check` prints nothing.

- [ ] **Step 4: Commit the UI baseline**

Run:

```bash
git commit -m "feat: complete Stage Lab UI baseline"
```

Expected: commit succeeds; none of the `.superpowers/` files are included.

---

### Task 2: Add Repository Hygiene for Local Artifacts

**Files:**

- Create: `.gitignore`

**Interfaces:**

- Consumes: Xcode and visual-companion generated local files.
- Produces: stable Git status that excludes machine-local artifacts without removing any tracked user data.

- [ ] **Step 1: Write the failing artifact check**

Run:

```bash
git check-ignore .superpowers/brainstorm/8259-1783664981/content/system-architecture.html
```

Expected: command exits non-zero because `.superpowers/` is not ignored yet.

- [ ] **Step 2: Create the ignore file**

Create `.gitignore` with exactly:

```gitignore
.DS_Store
.superpowers/
DerivedData/
*.xcuserstate
xcuserdata/
```

Do not run `git rm` for already tracked Xcode user files in this task.

- [ ] **Step 3: Verify artifacts are ignored**

Run:

```bash
git check-ignore -v .superpowers/brainstorm/8259-1783664981/content/system-architecture.html
git status --short
```

Expected: the first command reports the `.superpowers/` rule and `.superpowers/` no longer appears in `git status`.

- [ ] **Step 4: Commit repository hygiene**

Run:

```bash
git add .gitignore
git commit -m "chore: ignore local development artifacts"
```

Expected: one-file commit succeeds.

---

### Task 3: Add Unit and UI Test Targets

**Files:**

- Modify: `kpop.xcodeproj/project.pbxproj`
- Modify: `kpop.xcodeproj/xcshareddata/xcschemes/kpop.xcscheme`
- Create: `kpopTests/ProjectModelTests.swift`
- Create: `kpopUITests/AppLaunchTests.swift`

**Interfaces:**

- Consumes: module `kpop`, `DanceProject`, `ProjectPhase`, `PlaybackRate`, and the existing `kpop` scheme.
- Produces: buildable `kpopTests.xctest` and `kpopUITests.xctest` targets included in the shared scheme.

- [ ] **Step 1: Create the unit smoke tests**

Create `kpopTests/ProjectModelTests.swift`:

```swift
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
```

- [ ] **Step 2: Create the initial UI smoke test**

Create `kpopUITests/AppLaunchTests.swift`:

```swift
import XCTest

final class AppLaunchTests: XCTestCase {
    @MainActor
    func testCleanLaunchShowsHomeDashboard() throws {
        let app = XCUIApplication()
        app.launchArguments.append("--ui-testing")
        app.launch()

        XCTAssertTrue(app.navigationBars["Stage Lab"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["还没有项目"].waitForExistence(timeout: 5))
    }
}
```

At this point the UI test is expected to be nondeterministic because the app has not implemented `--ui-testing`; Task 4 fixes that behavior.

- [ ] **Step 3: Add synchronized test groups and products to the Xcode project**

Modify `project.pbxproj` with this exact ID map:

```text
A10000000000000000000001  kpopTests.xctest product reference
A10000000000000000000002  kpopUITests.xctest product reference
A10000000000000000000003  kpopTests synchronized root group
A10000000000000000000004  kpopUITests synchronized root group
A10000000000000000000005  kpopTests frameworks phase
A10000000000000000000006  kpopUITests frameworks phase
A10000000000000000000007  kpopTests resources phase
A10000000000000000000008  kpopUITests resources phase
A10000000000000000000009  kpopTests sources phase
A1000000000000000000000A  kpopUITests sources phase
A1000000000000000000000B  kpopTests container proxy
A1000000000000000000000C  kpopUITests container proxy
A1000000000000000000000D  kpopTests target dependency
A1000000000000000000000E  kpopUITests target dependency
A1000000000000000000000F  kpopTests native target
A10000000000000000000010  kpopUITests native target
A10000000000000000000011  kpopTests Debug configuration
A10000000000000000000012  kpopTests Release configuration
A10000000000000000000013  kpopTests configuration list
A10000000000000000000014  kpopUITests Debug configuration
A10000000000000000000015  kpopUITests Release configuration
A10000000000000000000016  kpopUITests configuration list
```

Add:

```text
PBXFileSystemSynchronizedRootGroup:
  kpopTests -> path kpopTests
  kpopUITests -> path kpopUITests

PBXFileReference products:
  kpopTests.xctest -> wrapper.cfbundle
  kpopUITests.xctest -> wrapper.cfbundle

PBXNativeTarget:
  kpopTests -> com.apple.product-type.bundle.unit-test
  kpopUITests -> com.apple.product-type.bundle.ui-testing
```

Each test target must contain empty `PBXSourcesBuildPhase`, `PBXFrameworksBuildPhase`, and `PBXResourcesBuildPhase` objects and list its matching synchronized root group in `fileSystemSynchronizedGroups`.

Add a `PBXContainerItemProxy` and `PBXTargetDependency` from each test target to the app target `677F700F2FC56BAF00BE0749`.

Add both targets to `PBXProject.targets`, both root groups to the main group, and both `.xctest` products to the Products group.

Use these exact unit-test build settings for Debug and Release:

```text
BUNDLE_LOADER = "$(TEST_HOST)";
CODE_SIGN_STYLE = Automatic;
GENERATE_INFOPLIST_FILE = YES;
IPHONEOS_DEPLOYMENT_TARGET = 18.0;
PRODUCT_BUNDLE_IDENTIFIER = fausyusgarygary.kpopTests;
PRODUCT_NAME = "$(TARGET_NAME)";
SDKROOT = iphoneos;
SWIFT_VERSION = 5.0;
TARGETED_DEVICE_FAMILY = "1,2";
TEST_HOST = "$(BUILT_PRODUCTS_DIR)/kpop.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/kpop";
```

Use these exact UI-test build settings for Debug and Release:

```text
CODE_SIGN_STYLE = Automatic;
GENERATE_INFOPLIST_FILE = YES;
IPHONEOS_DEPLOYMENT_TARGET = 18.0;
PRODUCT_BUNDLE_IDENTIFIER = fausyusgarygary.kpopUITests;
PRODUCT_NAME = "$(TARGET_NAME)";
SDKROOT = iphoneos;
SWIFT_VERSION = 5.0;
TARGETED_DEVICE_FAMILY = "1,2";
TEST_TARGET_NAME = kpop;
```

Set each target configuration list's default configuration to Release.

- [ ] **Step 4: Add test targets to the shared scheme**

In `kpop.xcscheme`, add both test targets as `BuildActionEntry` elements with `buildForTesting="YES"` and all other `buildFor...` attributes set to `NO`.

Replace the empty `TestAction` body with:

```xml
<Testables>
   <TestableReference skipped = "NO" parallelizable = "YES">
      <BuildableReference
         BuildableIdentifier = "primary"
         BlueprintIdentifier = "A1000000000000000000000F"
         BuildableName = "kpopTests.xctest"
         BlueprintName = "kpopTests"
         ReferencedContainer = "container:kpop.xcodeproj">
      </BuildableReference>
   </TestableReference>
   <TestableReference skipped = "NO" parallelizable = "NO">
      <BuildableReference
         BuildableIdentifier = "primary"
         BlueprintIdentifier = "A10000000000000000000010"
         BuildableName = "kpopUITests.xctest"
         BlueprintName = "kpopUITests"
         ReferencedContainer = "container:kpop.xcodeproj">
      </BuildableReference>
   </TestableReference>
</Testables>
```

- [ ] **Step 5: Verify project structure and run the unit tests**

Run:

```bash
xcodebuild -list -project kpop.xcodeproj
xcodebuild \
  -project kpop.xcodeproj \
  -scheme kpop \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:kpopTests \
  test
```

Expected: the list contains `kpop`, `kpopTests`, and `kpopUITests`; unit tests end with `** TEST SUCCEEDED **`.

- [ ] **Step 6: Commit the test target foundation**

Run:

```bash
git add \
  kpop.xcodeproj/project.pbxproj \
  kpop.xcodeproj/xcshareddata/xcschemes/kpop.xcscheme \
  kpopTests/ProjectModelTests.swift \
  kpopUITests/AppLaunchTests.swift
git diff --cached --check
git commit -m "test: add iOS unit and UI test targets"
```

Expected: four-file test foundation commit succeeds.

---

### Task 4: Make Test Launches Deterministic

**Files:**

- Create: `kpop/App/AppLaunchOptions.swift`
- Create: `kpop/App/ModelContainerFactory.swift`
- Create: `kpopTests/AppLaunchOptionsTests.swift`
- Modify: `kpop/kpopApp.swift`

**Interfaces:**

- Consumes: process argument `--ui-testing` and SwiftData model `DanceProject`.
- Produces: `AppLaunchOptions.usesInMemoryStore` and `ModelContainerFactory.make(options:) -> ModelContainer`.

- [ ] **Step 1: Write the failing launch-option tests**

Create `kpopTests/AppLaunchOptionsTests.swift`:

```swift
import SwiftData
import Testing
@testable import kpop

@MainActor
struct AppLaunchOptionsTests {
    @Test
    func normalLaunchUsesPersistentStore() {
        let options = AppLaunchOptions(arguments: ["kpop"])

        #expect(options.usesInMemoryStore == false)
    }

    @Test
    func uiTestLaunchUsesInMemoryStore() throws {
        let options = AppLaunchOptions(arguments: ["kpop", "--ui-testing"])
        let container = try ModelContainerFactory.make(options: options)
        let project = DanceProject(title: "Ephemeral")

        #expect(options.usesInMemoryStore)

        container.mainContext.insert(project)
        try container.mainContext.save()

        let projects = try container.mainContext.fetch(FetchDescriptor<DanceProject>())
        #expect(projects.map(\.title) == ["Ephemeral"])
    }
}
```

- [ ] **Step 2: Run the tests and confirm the missing types**

Run:

```bash
xcodebuild \
  -project kpop.xcodeproj \
  -scheme kpop \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:kpopTests/AppLaunchOptionsTests \
  test
```

Expected: compilation fails because `AppLaunchOptions` and `ModelContainerFactory` do not exist.

- [ ] **Step 3: Implement launch argument parsing**

Create `kpop/App/AppLaunchOptions.swift`:

```swift
import Foundation

struct AppLaunchOptions: Equatable {
    let usesInMemoryStore: Bool

    init(arguments: [String] = ProcessInfo.processInfo.arguments) {
        usesInMemoryStore = arguments.contains("--ui-testing")
    }
}
```

- [ ] **Step 4: Implement the model-container factory**

Create `kpop/App/ModelContainerFactory.swift`:

```swift
import SwiftData

enum ModelContainerFactory {
    @MainActor
    static func make(
        options: AppLaunchOptions = AppLaunchOptions()
    ) throws -> ModelContainer {
        let configuration = ModelConfiguration(
            isStoredInMemoryOnly: options.usesInMemoryStore
        )

        return try ModelContainer(
            for: DanceProject.self,
            configurations: configuration
        )
    }
}
```

- [ ] **Step 5: Route app startup through the factory**

Replace the `kpopApp.init()` implementation with:

```swift
init() {
    do {
        modelContainer = try ModelContainerFactory.make()
    } catch {
        fatalError("Failed to create SwiftData container: \(error)")
    }
}
```

Keep `WindowGroup`, `RootView`, and `.modelContainer(modelContainer)` unchanged.

- [ ] **Step 6: Run unit and UI tests**

Run:

```bash
xcodebuild \
  -project kpop.xcodeproj \
  -scheme kpop \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  test
```

Expected: all unit tests and `AppLaunchTests.testCleanLaunchShowsHomeDashboard` pass with `** TEST SUCCEEDED **`.

- [ ] **Step 7: Commit deterministic test startup**

Run:

```bash
git add \
  kpop/App/AppLaunchOptions.swift \
  kpop/App/ModelContainerFactory.swift \
  kpop/kpopApp.swift \
  kpopTests/AppLaunchOptionsTests.swift
git diff --cached --check
git commit -m "test: make app launches deterministic"
```

Expected: focused implementation commit succeeds.

---

### Task 5: Add Development, Staging, and Production Build Environments

**Files:**

- Modify: `kpop.xcodeproj/project.pbxproj`
- Create: `kpop.xcodeproj/xcshareddata/xcschemes/kpop-Staging.xcscheme`

**Interfaces:**

- Consumes: existing Debug and Release build configurations.
- Produces: `STAGE_LAB_ENVIRONMENT` build setting with values `development`, `staging`, or `production`, plus a release-like staging archive scheme.

- [ ] **Step 1: Prove that no environment setting exists**

Run:

```bash
xcodebuild \
  -project kpop.xcodeproj \
  -scheme kpop \
  -configuration Debug \
  -showBuildSettings | rg 'STAGE_LAB_ENVIRONMENT'
```

Expected: no match.

- [ ] **Step 2: Add environment settings to existing configurations**

In the app target Debug configuration add:

```text
STAGE_LAB_ENVIRONMENT = development;
INFOPLIST_KEY_STAGE_LAB_ENVIRONMENT = "$(STAGE_LAB_ENVIRONMENT)";
PRODUCT_BUNDLE_IDENTIFIER = fausyusgarygary.kpop.dev;
```

In the app target Release configuration add:

```text
STAGE_LAB_ENVIRONMENT = production;
INFOPLIST_KEY_STAGE_LAB_ENVIRONMENT = "$(STAGE_LAB_ENVIRONMENT)";
PRODUCT_BUNDLE_IDENTIFIER = fausyusgarygary.kpop;
```

The development bundle ID intentionally installs beside the production app. Existing simulator data under the old bundle remains untouched.

- [ ] **Step 3: Add release-like Staging configurations**

Use these exact new IDs:

```text
A10000000000000000000017  project Staging configuration
A10000000000000000000018  app target Staging configuration
A10000000000000000000019  kpopTests Staging configuration
A1000000000000000000001A  kpopUITests Staging configuration
```

Add project-level Staging configuration `A10000000000000000000017` by copying the existing project Release configuration exactly and changing only `name = Staging`.

Add app-target Staging configuration `A10000000000000000000018` by copying the existing app Release configuration and setting:

```text
name = Staging;
PRODUCT_BUNDLE_IDENTIFIER = fausyusgarygary.kpop.staging;
STAGE_LAB_ENVIRONMENT = staging;
INFOPLIST_KEY_STAGE_LAB_ENVIRONMENT = "$(STAGE_LAB_ENVIRONMENT)";
```

Add Staging to both corresponding `XCConfigurationList.buildConfigurations` arrays between Debug and Release.

Add unit and UI test Staging configurations `A10000000000000000000019` and `A1000000000000000000001A` by copying their Release settings and changing their bundle IDs to:

```text
fausyusgarygary.kpopTests.staging
fausyusgarygary.kpopUITests.staging
```

For the unit-test Staging configuration set:

```text
TEST_HOST = "$(BUILT_PRODUCTS_DIR)/kpop.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/kpop";
```

- [ ] **Step 4: Create the staging scheme**

Copy `kpop.xcscheme` to `kpop-Staging.xcscheme` and change:

```text
TestAction.buildConfiguration = Staging
LaunchAction.buildConfiguration = Staging
ProfileAction.buildConfiguration = Staging
AnalyzeAction.buildConfiguration = Staging
ArchiveAction.buildConfiguration = Staging
```

Keep all target blueprint IDs unchanged.

- [ ] **Step 5: Verify all three environments**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -configuration Debug -showBuildSettings | rg 'STAGE_LAB_ENVIRONMENT = development'
xcodebuild -project kpop.xcodeproj -scheme kpop-Staging -configuration Staging -showBuildSettings | rg 'STAGE_LAB_ENVIRONMENT = staging'
xcodebuild -project kpop.xcodeproj -scheme kpop -configuration Release -showBuildSettings | rg 'STAGE_LAB_ENVIRONMENT = production'
xcodebuild -project kpop.xcodeproj -scheme kpop-Staging -destination 'platform=iOS Simulator,name=iPhone 17' build
```

Expected: each `rg` prints one matching setting and the staging build ends with `** BUILD SUCCEEDED **`.

- [ ] **Step 6: Commit build environments**

Run:

```bash
git add \
  kpop.xcodeproj/project.pbxproj \
  kpop.xcodeproj/xcshareddata/xcschemes/kpop-Staging.xcscheme
git diff --cached --check
git commit -m "chore: add iOS build environments"
```

Expected: project and scheme commit succeeds.

---

### Task 6: Add One-Command Verification and Beginner Documentation

**Files:**

- Create: `scripts/verify-ios.sh`
- Create: `docs/development/ios-baseline.md`

**Interfaces:**

- Consumes: `kpop` and `kpop-Staging` shared schemes, iPhone 17 simulator, and all test targets.
- Produces: one command that verifies Debug tests, Staging build, and Release build without code signing.

- [ ] **Step 1: Create the verification script**

Create `scripts/verify-ios.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly project="kpop.xcodeproj"
readonly destination="${IOS_DESTINATION:-platform=iOS Simulator,name=iPhone 17}"

xcodebuild \
  -project "$project" \
  -scheme kpop \
  -destination "$destination" \
  test

xcodebuild \
  -project "$project" \
  -scheme kpop-Staging \
  -configuration Staging \
  -destination "$destination" \
  build

xcodebuild \
  -project "$project" \
  -scheme kpop \
  -configuration Release \
  -destination 'generic/platform=iOS Simulator' \
  build
```

Run:

```bash
chmod +x scripts/verify-ios.sh
```

- [ ] **Step 2: Create the beginner baseline guide**

Create `docs/development/ios-baseline.md` with exactly these sections and content:

```markdown
# iOS 工程基线

## 三套环境

- Development：日常 Xcode 开发，Bundle ID 为 `fausyusgarygary.kpop.dev`。
- Staging：连接测试云端并用于个人 TestFlight，Bundle ID 为 `fausyusgarygary.kpop.staging`。
- Production：正式 App Store 环境，Bundle ID 为 `fausyusgarygary.kpop`。

三套环境必须使用不同的云端项目、数据库、Bucket 和密钥。Stage 0 只建立 Xcode 配置，不连接云端。

## 两类测试

- `kpopTests`：不操作真实界面，快速检查模型和业务代码。
- `kpopUITests`：启动模拟器中的 App，检查用户能否看到和操作页面。

UI 测试传入 `--ui-testing`，App 会使用内存数据库，因此每次测试都从空项目开始，也不会删除开发数据。

## 验证命令

在工程根目录运行：

```bash
./scripts/verify-ios.sh
```

只有当命令最终返回退出码 0，并且输出中出现测试成功与三个构建成功结果时，Stage 0 才算通过。

如果本机模拟器名称变化，可以覆盖目标：

```bash
IOS_DESTINATION='platform=iOS Simulator,name=iPhone 17 Pro' ./scripts/verify-ios.sh
```

## 阅读顺序

1. `kpop/kpopApp.swift`：查看 App 如何启动。
2. `kpop/App/AppLaunchOptions.swift`：查看测试如何改变启动方式。
3. `kpop/App/ModelContainerFactory.swift`：查看本地数据库如何创建。
4. `kpopTests`：查看模型必须保证的行为。
5. `kpopUITests`：查看用户启动 App 后必须看到什么。
6. `scripts/verify-ios.sh`：查看交付前会执行哪些验证。
```

- [ ] **Step 3: Run the complete Stage 0 gate**

Run:

```bash
./scripts/verify-ios.sh
```

Expected, in order:

1. Debug unit and UI tests end with `** TEST SUCCEEDED **`.
2. Staging simulator build ends with `** BUILD SUCCEEDED **`.
3. Release generic simulator build ends with `** BUILD SUCCEEDED **`.

- [ ] **Step 4: Confirm no accidental files are included**

Run:

```bash
git status --short
git diff --check
```

Expected: only `scripts/verify-ios.sh` and `docs/development/ios-baseline.md` are modified/untracked for this task; `.superpowers/` remains hidden by `.gitignore`.

- [ ] **Step 5: Commit verification and documentation**

Run:

```bash
git add scripts/verify-ios.sh docs/development/ios-baseline.md
git diff --cached --check
git commit -m "chore: add iOS baseline verification"
```

Expected: final Stage 0 implementation commit succeeds.

---

## Stage 0 Completion Checklist

- [ ] Existing six-file UI baseline is committed without visual regressions.
- [ ] `.superpowers/` and local Xcode artifacts are ignored.
- [ ] `kpopTests` and `kpopUITests` appear in `xcodebuild -list`.
- [ ] UI tests always start with an empty in-memory SwiftData store.
- [ ] Development, Staging, and Production have distinct environment values and bundle IDs.
- [ ] `./scripts/verify-ios.sh` passes on the iPhone 17 simulator.
- [ ] The user launches the Development app in Xcode and confirms the home, import, analysis, dancer-selection, and practice routes still work.
- [ ] No Firebase, Google Cloud, AI, CloudKit, StoreKit, or new product behavior has entered the codebase.

After this checklist is accepted, write a separate Stage 1 plan for the local domain model, formal analysis state machine, repositories, file stores, and fake cloud services.
