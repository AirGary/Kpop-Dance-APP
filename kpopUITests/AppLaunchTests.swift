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
