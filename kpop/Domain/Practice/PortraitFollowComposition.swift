import AVFoundation
import CoreGraphics

enum PortraitFollowCompositionBuilder {
    static func makeItem(asset: AVAsset, frames: [PortraitFollowFrame]) async throws -> AVPlayerItem {
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard let track = tracks.first else {
            return AVPlayerItem(asset: asset)
        }

        let duration = try await asset.load(.duration)
        let naturalSize = try await track.load(.naturalSize)
        let preferredTransform = try await track.load(.preferredTransform)
        let sourceBounds = CGRect(origin: .zero, size: naturalSize)
        let uprightBounds = sourceBounds.applying(preferredTransform).standardized
        guard sourceBounds.width > 0,
              sourceBounds.height > 0,
              uprightBounds.width > 0,
              uprightBounds.height > 0,
              duration.isNumeric,
              duration > .zero else {
            return AVPlayerItem(asset: asset)
        }

        let renderSize = portraitRenderSize(for: uprightBounds.size)
        let composition = AVMutableVideoComposition()
        composition.renderSize = renderSize
        composition.frameDuration = CMTime(value: 1, timescale: 30)
        composition.instructions = makeInstructions(
            track: track,
            duration: duration,
            sourceBounds: sourceBounds,
            uprightBounds: uprightBounds,
            preferredTransform: preferredTransform,
            renderSize: renderSize,
            frames: frames
        )

        let item = AVPlayerItem(asset: asset)
        item.videoComposition = composition
        return item
    }

    private static func portraitRenderSize(for sourceSize: CGSize) -> CGSize {
        let height = evenPositive(sourceSize.height)
        let width = evenPositive(height * PortraitFollowPlan.targetAspect)
        return CGSize(width: width, height: height)
    }

    private static func makeInstructions(
        track: AVAssetTrack,
        duration: CMTime,
        sourceBounds: CGRect,
        uprightBounds: CGRect,
        preferredTransform: CGAffineTransform,
        renderSize: CGSize,
        frames: [PortraitFollowFrame]
    ) -> [AVVideoCompositionInstructionProtocol] {
        let frames = frames.isEmpty ? [.fullSource] : frames
        var instructions: [AVVideoCompositionInstructionProtocol] = []
        var startIndex = 0

        while startIndex < frames.count {
            let isTracking = cropRectangle(
                for: frames[startIndex],
                sourceBounds: sourceBounds,
                uprightBounds: uprightBounds,
                preferredTransform: preferredTransform
            ) != nil
            var endIndex = startIndex + 1
            while endIndex < frames.count {
                let nextIsTracking = cropRectangle(
                    for: frames[endIndex],
                    sourceBounds: sourceBounds,
                    uprightBounds: uprightBounds,
                    preferredTransform: preferredTransform
                ) != nil
                guard nextIsTracking == isTracking else { break }
                endIndex += 1
            }

            let timeRange = frameTimeRange(
                from: startIndex,
                to: endIndex,
                frameCount: frames.count,
                duration: duration
            )
            let startCrop = cropRectangle(
                for: frames[startIndex],
                sourceBounds: sourceBounds,
                uprightBounds: uprightBounds,
                preferredTransform: preferredTransform
            ) ?? sourceBounds
            let endCrop = cropRectangle(
                for: frames[endIndex - 1],
                sourceBounds: sourceBounds,
                uprightBounds: uprightBounds,
                preferredTransform: preferredTransform
            ) ?? sourceBounds

            let layerInstruction = AVMutableVideoCompositionLayerInstruction(assetTrack: track)
            layerInstruction.setCropRectangleRamp(
                fromStartCropRectangle: startCrop,
                toEndCropRectangle: endCrop,
                timeRange: timeRange
            )
            layerInstruction.setTransformRamp(
                fromStart: transform(
                    for: startCrop,
                    isTracking: isTracking,
                    uprightBounds: uprightBounds,
                    preferredTransform: preferredTransform,
                    renderSize: renderSize
                ),
                toEnd: transform(
                    for: endCrop,
                    isTracking: isTracking,
                    uprightBounds: uprightBounds,
                    preferredTransform: preferredTransform,
                    renderSize: renderSize
                ),
                timeRange: timeRange
            )

            let instruction = AVMutableVideoCompositionInstruction()
            instruction.timeRange = timeRange
            instruction.layerInstructions = [layerInstruction]
            instructions.append(instruction)
            startIndex = endIndex
        }

        return instructions
    }

    private static func cropRectangle(
        for frame: PortraitFollowFrame,
        sourceBounds: CGRect,
        uprightBounds: CGRect,
        preferredTransform: CGAffineTransform
    ) -> CGRect? {
        guard let crop = frame.crop,
              crop.minX.isFinite,
              crop.minY.isFinite,
              crop.width.isFinite,
              crop.height.isFinite,
              crop.minX >= 0,
              crop.minY >= 0,
              crop.width > 0,
              crop.height > 0,
              crop.maxX <= 1,
              crop.maxY <= 1 else {
            return nil
        }

        let uprightCrop = CGRect(
            x: uprightBounds.minX + crop.minX * uprightBounds.width,
            y: uprightBounds.minY + crop.minY * uprightBounds.height,
            width: crop.width * uprightBounds.width,
            height: crop.height * uprightBounds.height
        )
        let sourceCrop = uprightCrop
            .applying(preferredTransform.inverted())
            .standardized
            .intersection(sourceBounds)
        return sourceCrop.width > 0 && sourceCrop.height > 0 ? sourceCrop : nil
    }

    private static func transform(
        for sourceCrop: CGRect,
        isTracking: Bool,
        uprightBounds: CGRect,
        preferredTransform: CGAffineTransform,
        renderSize: CGSize
    ) -> CGAffineTransform {
        let uprightCrop = sourceCrop.applying(preferredTransform).standardized
        if isTracking {
            let scaleX = renderSize.width / uprightCrop.width
            let scaleY = renderSize.height / uprightCrop.height
            return preferredTransform
                .translatedBy(x: -uprightCrop.minX, y: -uprightCrop.minY)
                .scaledBy(x: scaleX, y: scaleY)
        }

        let scale = min(renderSize.width / uprightBounds.width, renderSize.height / uprightBounds.height)
        let offsetX = (renderSize.width - uprightBounds.width * scale) / 2
        let offsetY = (renderSize.height - uprightBounds.height * scale) / 2
        return preferredTransform
            .translatedBy(x: -uprightBounds.minX, y: -uprightBounds.minY)
            .scaledBy(x: scale, y: scale)
            .translatedBy(x: offsetX, y: offsetY)
    }

    private static func frameTimeRange(
        from startIndex: Int,
        to endIndex: Int,
        frameCount: Int,
        duration: CMTime
    ) -> CMTimeRange {
        let start = CMTimeMultiplyByRatio(duration, multiplier: Int32(startIndex), divisor: Int32(frameCount))
        let end = CMTimeMultiplyByRatio(duration, multiplier: Int32(endIndex), divisor: Int32(frameCount))
        return CMTimeRange(start: start, end: end)
    }

    private static func evenPositive(_ value: CGFloat) -> CGFloat {
        max(2, (value.rounded() / 2).rounded() * 2)
    }
}
