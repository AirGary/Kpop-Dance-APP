import SwiftUI

private struct AnalysisServiceKey: EnvironmentKey {
    static let defaultValue: (any AnalysisService)? = nil
}

private struct AnalysisAPIClientKey: EnvironmentKey {
    static let defaultValue: AnalysisAPIClient? = nil
}

private struct AnalysisPackageDownloaderKey: EnvironmentKey {
    static let defaultValue: (any AnalysisPackageDownloader)? = nil
}

extension EnvironmentValues {
    var analysisService: (any AnalysisService)? {
        get { self[AnalysisServiceKey.self] }
        set { self[AnalysisServiceKey.self] = newValue }
    }

    var analysisAPIClient: AnalysisAPIClient? {
        get { self[AnalysisAPIClientKey.self] }
        set { self[AnalysisAPIClientKey.self] = newValue }
    }

    var analysisPackageDownloader: (any AnalysisPackageDownloader)? {
        get { self[AnalysisPackageDownloaderKey.self] }
        set { self[AnalysisPackageDownloaderKey.self] = newValue }
    }
}
