import Foundation
import SwiftData

@MainActor
final class SwiftDataDanceProjectRepository: DanceProjectRepository {
    private let modelContainer: ModelContainer
    private let modelContext: ModelContext

    init(modelContext: ModelContext) {
        self.modelContainer = modelContext.container
        self.modelContext = modelContext
    }

    func fetchAll() throws -> [DanceProject] {
        let descriptor = FetchDescriptor<DanceProject>(
            sortBy: [SortDescriptor(\DanceProject.updatedAt, order: .reverse)]
        )
        return try modelContext.fetch(descriptor)
    }

    func fetch(id: UUID) throws -> DanceProject? {
        let descriptor = FetchDescriptor<DanceProject>(
            predicate: #Predicate { $0.id == id }
        )
        return try modelContext.fetch(descriptor).first
    }

    func insert(_ project: DanceProject) {
        modelContext.insert(project)
    }

    func save() throws {
        guard modelContext.hasChanges else { return }
        try modelContext.save()
    }

    func delete(_ project: DanceProject) {
        modelContext.delete(project)
    }
}
