import Foundation
import SwiftData
import Testing
@testable import kpop

@MainActor
struct DanceProjectRepositoryTests {
    @Test
    func fetchAllSortsMostRecentlyUpdatedFirst() throws {
        let repository = try makeRepository()
        let older = DanceProject(
            updatedAt: Date(timeIntervalSince1970: 100),
            title: "Older"
        )
        let newer = DanceProject(
            updatedAt: Date(timeIntervalSince1970: 200),
            title: "Newer"
        )
        repository.insert(older)
        repository.insert(newer)

        let projects = try repository.fetchAll()

        #expect(projects.map(\.id) == [newer.id, older.id])
    }

    @Test
    func fetchFindsAProjectByID() throws {
        let repository = try makeRepository()
        let project = DanceProject(title: "Lookup")
        repository.insert(project)

        #expect(try repository.fetch(id: project.id)?.title == "Lookup")
        #expect(try repository.fetch(id: UUID()) == nil)
    }

    @Test
    func insertAndSavePersistProjectChanges() throws {
        let repository = try makeRepository()
        let project = DanceProject(title: "Draft")
        repository.insert(project)
        try repository.save()

        project.title = "Saved"
        try repository.save()

        #expect(try repository.fetch(id: project.id)?.title == "Saved")
    }

    @Test
    func deleteRemovesAProject() throws {
        let repository = try makeRepository()
        let project = DanceProject(title: "Delete")
        repository.insert(project)
        try repository.save()

        repository.delete(project)
        try repository.save()

        #expect(try repository.fetch(id: project.id) == nil)
    }

    @Test
    func cloudMetadataUsesMigrationSafeDefaults() {
        let project = DanceProject(title: "Defaults")

        #expect(project.sourceFingerprint.isEmpty)
        #expect(project.remoteJobId == nil)
        #expect(project.analysisSchemaVersion == nil)
        #expect(project.analysisPackageRelativePath == nil)
        #expect(project.lastPracticedAt == nil)
    }

    private func makeRepository() throws -> SwiftDataDanceProjectRepository {
        let configuration = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(
            for: DanceProject.self,
            configurations: configuration
        )
        return SwiftDataDanceProjectRepository(modelContext: container.mainContext)
    }
}
