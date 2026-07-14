import SwiftData
import Testing
@testable import kpop

@MainActor
struct AppLaunchOptionsTests {
    @Test
    func normalLaunchUsesPersistentStore() {
        let options = AppLaunchOptions(arguments: ["kpop"])

        #expect(options.usesInMemoryStore == false)
    }

    @Test
    func uiTestLaunchUsesInMemoryStore() throws {
        let options = AppLaunchOptions(arguments: ["kpop", "--ui-testing"])
        let container = try ModelContainerFactory.make(options: options)
        let project = DanceProject(title: "Ephemeral")

        #expect(options.usesInMemoryStore)

        container.mainContext.insert(project)
        try container.mainContext.save()

        let projects = try container.mainContext.fetch(FetchDescriptor<DanceProject>())
        #expect(projects.map(\.title) == ["Ephemeral"])
    }
}
