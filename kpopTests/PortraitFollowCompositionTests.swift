import AVFoundation
import CoreGraphics
import CoreVideo
import Testing
@testable import kpop

private enum TestVideoAsset {
    static func make(
        size: CGSize,
        duration: Double,
        preferredTransform: CGAffineTransform = .identity
    ) async throws -> AVURLAsset {
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
        input.transform = preferredTransform
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
func trackingPlanUsesExactPortraitSizeAndCropAndTransformRamps() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(
        asset: asset,
        frames: [
            .tracking(NormalizedRect(minX: 0.2, minY: 0, width: 0.5625, height: 1)),
            .tracking(NormalizedRect(minX: 0.25, minY: 0, width: 0.5625, height: 1))
        ]
    )

    let composition = try #require(item.videoComposition)
    #expect(composition.renderSize.width == 594)
    #expect(composition.renderSize.height == 1056)
    #expect(composition.renderSize.width * 16 == composition.renderSize.height * 9)

    let ramp = try cropAndTransformRamp(in: composition)
    #expect(ramp.startCrop == CGRect(x: 384, y: 0, width: 1080, height: 1080))
    #expect(ramp.endCrop == CGRect(x: 480, y: 0, width: 1080, height: 1080))
    #expect(ramp.timeRange.start == .zero)
    #expect(CMTimeGetSeconds(ramp.timeRange.duration) == 2)
    expectTransform(
        ramp.startTransform,
        equals: CGAffineTransform(a: 0.55, b: 0, c: 0, d: 44.0 / 45.0, tx: -211.2, ty: 0)
    )
    expectTransform(
        ramp.endTransform,
        equals: CGAffineTransform(a: 0.55, b: 0, c: 0, d: 44.0 / 45.0, tx: -264, ty: 0)
    )
}

@Test
func fullSourcePlanUsesCenteredAspectFitCropAndTransform() async throws {
    let asset = try await TestVideoAsset.make(size: CGSize(width: 1920, height: 1080), duration: 2)
    let item = try await PortraitFollowCompositionBuilder.makeItem(asset: asset, frames: [.fullSource])

    let composition = try #require(item.videoComposition)
    let ramp = try cropAndTransformRamp(in: composition)
    #expect(ramp.startCrop == CGRect(x: 0, y: 0, width: 1920, height: 1080))
    #expect(ramp.endCrop == ramp.startCrop)
    expectTransform(
        ramp.startTransform,
        equals: CGAffineTransform(a: 0.309375, b: 0, c: 0, d: 0.309375, tx: 0, ty: 360.9375)
    )
    #expect(ramp.endTransform == ramp.startTransform)
}

@Test
func rotatedAsymmetricSourceUsesUprightCropAndTransform() async throws {
    let asset = try await TestVideoAsset.make(
        size: CGSize(width: 320, height: 180),
        duration: 2,
        preferredTransform: CGAffineTransform(a: 0, b: 1, c: -1, d: 0, tx: 180, ty: 0)
    )
    let item = try await PortraitFollowCompositionBuilder.makeItem(
        asset: asset,
        frames: [
            .tracking(NormalizedRect(minX: 0.25, minY: 0.125, width: 0.5, height: 0.75))
        ]
    )

    let composition = try #require(item.videoComposition)
    #expect(composition.renderSize == CGSize(width: 180, height: 320))

    let ramp = try cropAndTransformRamp(in: composition)
    #expect(ramp.startCrop == CGRect(x: 40, y: 45, width: 240, height: 90))
    #expect(ramp.endCrop == ramp.startCrop)
    expectTransform(
        ramp.startTransform,
        equals: CGAffineTransform(a: 0, b: 4.0 / 3.0, c: -2, d: 0, tx: 270, ty: -160.0 / 3.0)
    )
    #expect(ramp.endTransform == ramp.startTransform)
}

private struct CropAndTransformRamp {
    let startCrop: CGRect
    let endCrop: CGRect
    let startTransform: CGAffineTransform
    let endTransform: CGAffineTransform
    let timeRange: CMTimeRange
}

private func expectTransform(_ actual: CGAffineTransform, equals expected: CGAffineTransform) {
    let tolerance = 0.0001
    #expect(abs(actual.a - expected.a) < tolerance)
    #expect(abs(actual.b - expected.b) < tolerance)
    #expect(abs(actual.c - expected.c) < tolerance)
    #expect(abs(actual.d - expected.d) < tolerance)
    #expect(abs(actual.tx - expected.tx) < tolerance)
    #expect(abs(actual.ty - expected.ty) < tolerance)
}

private func cropAndTransformRamp(
    in composition: AVVideoComposition
) throws -> CropAndTransformRamp {
    let instruction = try #require(composition.instructions.first as? AVVideoCompositionInstruction)
    let layerInstruction = try #require(instruction.layerInstructions.first)
    var startCrop = CGRect.zero
    var endCrop = CGRect.zero
    var cropTimeRange = CMTimeRange.zero
    #expect(layerInstruction.getCropRectangleRamp(
        for: CMTime(value: 1, timescale: 30),
        startCropRectangle: &startCrop,
        endCropRectangle: &endCrop,
        timeRange: &cropTimeRange
    ))

    var startTransform = CGAffineTransform.identity
    var endTransform = CGAffineTransform.identity
    var transformTimeRange = CMTimeRange.zero
    #expect(layerInstruction.getTransformRamp(
        for: CMTime(value: 1, timescale: 30),
        start: &startTransform,
        end: &endTransform,
        timeRange: &transformTimeRange
    ))
    #expect(transformTimeRange == cropTimeRange)

    return CropAndTransformRamp(
        startCrop: startCrop,
        endCrop: endCrop,
        startTransform: startTransform,
        endTransform: endTransform,
        timeRange: cropTimeRange
    )
}
