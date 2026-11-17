import AVFoundation
import CoreGraphics

enum PortraitFollowCompositionBuilder {
    struct TimedFrame: Equatable, Sendable {
        let timeSeconds: Double
        let frame: PortraitFollowFrame
    }

    static func memberFancamTimedFrames(for poseTrack: [AnalysisPoseFrame]) -> [TimedFrame] {
        let orderedTrack = poseTrack
            .filter { $0.timeSeconds.isFinite }
            .sorted { $0.timeSeconds < $1.timeSeconds }
        return orderedTrack.map { frame in
            TimedFrame(
                timeSeconds: frame.timeSeconds,
                frame: MemberFancamPlan.make(track: orderedTrack, at: frame.timeSeconds)
            )
        }
    }

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

    static func makeItem(asset: AVAsset, timedFrames: [TimedFrame]) async throws -> AVPlayerItem {
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard let track = tracks.first else { return AVPlayerItem(asset: asset) }
        let duration = try await asset.load(.duration)
        let naturalSize = try await track.load(.naturalSize)
        let preferredTransform = try await track.load(.preferredTransform)
        let sourceBounds = CGRect(origin: .zero, size: naturalSize)
        let uprightBounds = sourceBounds.applying(preferredTransform).standardized
        guard sourceBounds.width > 0, sourceBounds.height > 0,
              uprightBounds.width > 0, uprightBounds.height > 0,
              duration.isNumeric, duration > .zero else { return AVPlayerItem(asset: asset) }

        let valid = timedFrames
            .filter { $0.timeSeconds.isFinite && $0.timeSeconds >= 0 && $0.timeSeconds < duration.seconds }
            .sorted { $0.timeSeconds < $1.timeSeconds }
        guard valid.isEmpty == false else { return AVPlayerItem(asset: asset) }
        let renderSize = portraitRenderSize(for: uprightBounds.size)
        let composition = AVMutableVideoComposition()
        composition.renderSize = renderSize
        composition.frameDuration = CMTime(value: 1, timescale: 30)
        composition.instructions = makeTimedInstructions(
            track: track, duration: duration, sourceBounds: sourceBounds, uprightBounds: uprightBounds,
            preferredTransform: preferredTransform, renderSize: renderSize, frames: valid
        )
        let item = AVPlayerItem(asset: asset)
        item.videoComposition = composition
        return item
    }

    private static func makeTimedInstructions(
        track: AVAssetTrack,
        duration: CMTime,
        sourceBounds: CGRect,
        uprightBounds: CGRect,
        preferredTransform: CGAffineTransform,
        renderSize: CGSize,
        frames: [TimedFrame]
    ) -> [AVVideoCompositionInstructionProtocol] {
        let initial = TimedFrame(timeSeconds: 0, frame: .fullSource)
        let allFrames = (frames.first?.timeSeconds ?? 0) > 0 ? [initial] + frames : frames
        return allFrames.indices.compactMap { index in
            let start = allFrames[index]
            let endTime = index + 1 < allFrames.count ? allFrames[index + 1].timeSeconds : duration.seconds
            guard endTime > start.timeSeconds else { return nil }
            let startCrop = cropRectangle(for: start.frame, sourceBounds: sourceBounds, uprightBounds: uprightBounds, preferredTransform: preferredTransform) ?? sourceBounds
            let endCrop = index + 1 < allFrames.count
                ? (cropRectangle(for: allFrames[index + 1].frame, sourceBounds: sourceBounds, uprightBounds: uprightBounds, preferredTransform: preferredTransform) ?? sourceBounds)
                : startCrop
            let isTracking = start.frame.crop != nil && (index + 1 == allFrames.count || allFrames[index + 1].frame.crop != nil)
            let timeRange = CMTimeRange(start: CMTime(seconds: start.timeSeconds, preferredTimescale: 600), duration: CMTime(seconds: endTime - start.timeSeconds, preferredTimescale: 600))
            let layer = AVMutableVideoCompositionLayerInstruction(assetTrack: track)
            layer.setCropRectangleRamp(fromStartCropRectangle: startCrop, toEndCropRectangle: endCrop, timeRange: timeRange)
            layer.setTransformRamp(
                fromStart: transform(for: startCrop, isTracking: isTracking, uprightBounds: uprightBounds, preferredTransform: preferredTransform, renderSize: renderSize),
                toEnd: transform(for: endCrop, isTracking: isTracking, uprightBounds: uprightBounds, preferredTransform: preferredTransform, renderSize: renderSize),
                timeRange: timeRange
            )
            let instruction = AVMutableVideoCompositionInstruction()
            instruction.timeRange = timeRange
            instruction.layerInstructions = [layer]
            return instruction
        }
    }

    private static func portraitRenderSize(for sourceSize: CGSize) -> CGSize {
        let height = max(32, Int(sourceSize.height.rounded(.down)) / 32 * 32)
        return CGSize(width: CGFloat(height / 16 * 9), height: CGFloat(height))
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
            let renderTransform = CGAffineTransform.identity
                .scaledBy(x: scaleX, y: scaleY)
                .translatedBy(x: -uprightCrop.minX, y: -uprightCrop.minY)
            return preferredTransform.concatenating(renderTransform)
        }

        let scale = min(renderSize.width / uprightBounds.width, renderSize.height / uprightBounds.height)
        let offsetX = (renderSize.width - uprightBounds.width * scale) / 2
        let offsetY = (renderSize.height - uprightBounds.height * scale) / 2
        let renderTransform = CGAffineTransform.identity
            .translatedBy(x: offsetX, y: offsetY)
            .scaledBy(x: scale, y: scale)
            .translatedBy(x: -uprightBounds.minX, y: -uprightBounds.minY)
        return preferredTransform.concatenating(renderTransform)
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
}
