import Foundation

nonisolated struct JobsAPIConfiguration: Equatable, Sendable {
    let baseURL: URL
    let bearerToken: String
    let pairingToken: String?

    init(baseURL: URL, bearerToken: String, pairingToken: String? = nil) {
        self.baseURL = baseURL
        self.bearerToken = bearerToken
        self.pairingToken = pairingToken
    }

    static func from(infoDictionary: [String: Any]) throws -> JobsAPIConfiguration? {
        guard let environment = infoDictionary["STAGE_LAB_ENVIRONMENT"] as? String else {
            return nil
        }
        guard environment == "development" || environment == "local-ai" else {
            return nil
        }
        guard let value = infoDictionary["STAGE_LAB_API_BASE_URL"] as? String,
              let url = URL(string: value),
              url.port == 8000,
              url.scheme == "http"
        else {
            throw JobsAPIError.invalidConfiguration
        }

        let loopbackHosts = Set(["127.0.0.1", "localhost", "::1"])
        if environment == "development" && url.host != "127.0.0.1" {
            throw JobsAPIError.invalidConfiguration
        }
        let pairingToken = infoDictionary["STAGE_LAB_PAIRING_TOKEN"] as? String
        if environment == "local-ai", !loopbackHosts.contains(url.host ?? ""), pairingToken?.isEmpty != false {
            return nil
        }
        return JobsAPIConfiguration(
            baseURL: url,
            bearerToken: "dev-user-a",
            pairingToken: pairingToken
        )
    }
}
