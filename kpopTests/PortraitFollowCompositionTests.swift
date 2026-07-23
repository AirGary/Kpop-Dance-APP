import AVFoundation
import CoreVideo
import Testing
@testable import kpop

private enum TestVideoAsset {
    static func make(size: CGSize, duration: Double) async throws -> AVURLAsset {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("mov")
        let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let input = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: Int(size.width),
                AVVideoHeightKey: Int(size.height)
            ]
        )
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
            ]
        )
        writer.add(input)
        #expect(writer.startWriting())
        writer.startSession(atSourceTime: .zero)

        let frameCount = Int(duration * 30)
        for index in 0..<frameCount {
            while !input.isReadyForMoreMediaData {
                await Task.yield()
            }

            var buffer: CVPixelBuffer?
            let status = CVPixelBufferCreate(
                kCFAllocatorDefault,
                Int(size.width),
                Int(size.height),
                kCVPixelFormatType_32BGRA,
                nil,
                &buffer
            )
            #expect(status == kCVReturnSuccess)
            #expect(adaptor.append(
                try #require(buffer),
                withPresentationTime: CMTime(value: Int64(index), timescale: 30)
            ))
        }

        input.markAsFinished()
        await writer.finishWriting()
        guard writer.status == .completed else {
            throw writer.error ?? CocoaError(.fileWriteUnknown)
        }
        return AVURLAsset(url: url)
    }
}

@Test
func trackingPlanProducesNineBySixteenRenderSizeAndCropRamp() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(
        asset: asset,
        frames: [
            .tracking(NormalizedRect(minX: 0.2, minY: 0, width: 0.5625, height: 1)),
            .tracking(NormalizedRect(minX: 0.25, minY: 0, width: 0.5625, height: 1))
        ]
    )

    let composition = try #require(item.videoComposition)
    #expect(abs(composition.renderSize.width / composition.renderSize.height - 9.0 / 16.0) < 0.001)
    #expect(composition.instructions.isEmpty == false)
}

@Test
func fullSourcePlanUsesAspectFitTransformInsteadOfDroppingPlayback() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(asset: asset, frames: [.fullSource])

    #expect(item.asset === asset)
    #expect(item.videoComposition != nil)
}
