import SwiftData

enum ModelContainerFactory {
    @MainActor
    static func make() throws -> ModelContainer {
        try make(options: AppLaunchOptions())
    }

    @MainActor
    static func make(options: AppLaunchOptions) throws -> ModelContainer {
        let schema = Schema([DanceProject.self])
        let configuration = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: options.usesInMemoryStore
        )

        return try ModelContainer(
            for: schema,
            configurations: configuration
        )
    }
}
