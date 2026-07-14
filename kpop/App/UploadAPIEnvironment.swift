import SwiftUI

private struct UploadRunnerKey: EnvironmentKey {
    static let defaultValue: UploadRunner? = nil
}

extension EnvironmentValues {
    var uploadRunner: UploadRunner? {
        get { self[UploadRunnerKey.self] }
        set { self[UploadRunnerKey.self] = newValue }
    }
}
