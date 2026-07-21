import Foundation

nonisolated protocol AnalysisPackageDownloader: Sendable {
    func downloadPackage(result: AnalysisResultDescriptor) async throws -> Data
}
