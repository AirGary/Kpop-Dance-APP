import SwiftUI

private struct JobsAPIClientKey: EnvironmentKey {
    static let defaultValue: JobsAPIClient? = nil
}

extension EnvironmentValues {
    var jobsAPIClient: JobsAPIClient? {
        get { self[JobsAPIClientKey.self] }
        set { self[JobsAPIClientKey.self] = newValue }
    }
}
