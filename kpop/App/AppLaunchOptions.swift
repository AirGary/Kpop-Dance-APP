import Foundation

struct AppLaunchOptions: Equatable {
    let usesInMemoryStore: Bool

    init(arguments: [String] = ProcessInfo.processInfo.arguments) {
        usesInMemoryStore = arguments.contains("--ui-testing")
    }
}
