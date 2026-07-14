import Foundation

nonisolated struct JobsAPIConfiguration: Equatable, Sendable {
    let baseURL: URL
    let bearerToken: String

    static func from(infoDictionary: [String: Any]) throws -> JobsAPIConfiguration? {
        guard infoDictionary["STAGE_LAB_ENVIRONMENT"] as? String == "development" else {
            return nil
        }
        guard
            let value = infoDictionary["STAGE_LAB_API_BASE_URL"] as? String,
            let url = URL(string: value),
            url.scheme == "http",
            url.host == "127.0.0.1",
            url.port == 8000
        else {
            throw JobsAPIError.invalidConfiguration
        }
        return JobsAPIConfiguration(baseURL: url, bearerToken: "dev-user-a")
    }
}
