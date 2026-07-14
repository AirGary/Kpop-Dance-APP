import AVFoundation
import Testing
@testable import kpop

struct VideoCompressionServiceTests {
    @Test
    func liveConfigurationTargets1080pMP4() {
        #expect(VideoCompressionService.presetName == AVAssetExportPreset1920x1080)
        #expect(VideoCompressionService.outputFileType == .mp4)
    }
}
