import Foundation
import Testing
@testable import kpop

struct JobsAPIConfigurationTests {
    @Test
    func developmentInfoCreatesLocalConfiguration() throws {
        let result = try JobsAPIConfiguration.from(infoDictionary: [
            "STAGE_LAB_ENVIRONMENT": "development",
            "STAGE_LAB_API_BASE_URL": "http://127.0.0.1:8000"
        ])
        let configuration = try #require(result)

        #expect(configuration.baseURL.absoluteString == "http://127.0.0.1:8000")
        #expect(configuration.bearerToken == "dev-user-a")
    }

    @Test(arguments: ["staging", "production"])
    func deployedEnvironmentsDoNotUseLocalConfiguration(environment: String) throws {
        let configuration = try JobsAPIConfiguration.from(infoDictionary: [
            "STAGE_LAB_ENVIRONMENT": environment,
            "STAGE_LAB_API_BASE_URL": "http://127.0.0.1:8000"
        ])

        #expect(configuration == nil)
    }

    @Test
    func invalidDevelopmentURLIsRejected() {
        #expect(throws: JobsAPIError.invalidConfiguration) {
            try JobsAPIConfiguration.from(infoDictionary: [
                "STAGE_LAB_ENVIRONMENT": "development",
                "STAGE_LAB_API_BASE_URL": "not a URL"
            ])
        }
    }
}
