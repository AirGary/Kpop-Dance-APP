import Foundation

nonisolated struct HTTPTransport: Sendable {
    let send: @Sendable (URLRequest) async throws -> (Data, URLResponse)

    static let live = HTTPTransport { request in
        try await URLSession.shared.data(for: request)
    }
}
