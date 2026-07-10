import SwiftData

enum ModelContainerFactory {
    @MainActor
    static func make() throws -> ModelContainer {
        try make(options: AppLaunchOptions())
    }

    @MainActor
    static func make(options: AppLaunchOptions) throws -> ModelContainer {
        let configuration = ModelConfiguration(
            isStoredInMemoryOnly: options.usesInMemoryStore
        )

        return try ModelContainer(
            for: DanceProject.self,
            configurations: configuration
        )
    }
}
