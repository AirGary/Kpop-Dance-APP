import Foundation

@MainActor
protocol DanceProjectRepository {
    func fetchAll() throws -> [DanceProject]
    func fetch(id: UUID) throws -> DanceProject?
    func insert(_ project: DanceProject)
    func save() throws
    func delete(_ project: DanceProject)
}
