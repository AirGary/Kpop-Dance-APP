import Foundation

nonisolated enum UploadNetworkPolicy {
    static func configuration(allowsCellular: Bool) -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.allowsCellularAccess = true
        configuration.allowsExpensiveNetworkAccess = allowsCellular
        configuration.waitsForConnectivity = true
        return configuration
    }

    static func transport(allowsCellular: Bool) -> HTTPTransport {
        let session = URLSession(configuration: configuration(allowsCellular: allowsCellular))
        return .urlSession(session)
    }
}
