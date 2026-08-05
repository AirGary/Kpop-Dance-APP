import XCTest

final class IdentityConfirmationFlowUITests: XCTestCase {
    @MainActor
    func testIdentityConfirmationFixtureShowsBothChoices() throws {
        let app = XCUIApplication()
        app.launchArguments += ["--ui-testing", "--ui-testing-identity-confirmation"]
        app.launch()

        XCTAssertTrue(app.navigationBars["身份确认"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["identity-confirmation-same"].exists)
        XCTAssertTrue(app.buttons["identity-confirmation-different"].exists)
        XCTAssertTrue(app.staticTexts["是否仍是所选舞者？"].exists)
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", "图片不可用")).count, 2)

        app.buttons["identity-confirmation-same"].tap()
        XCTAssertTrue(app.staticTexts["提交失败，请重试。"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["identity-confirmation-same"].isEnabled)
    }
}
