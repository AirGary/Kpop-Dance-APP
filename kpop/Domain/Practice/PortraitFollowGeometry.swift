import CoreGraphics
import Foundation

nonisolated struct NormalizedRect: Equatable, Sendable {
    let minX: Double
    let minY: Double
    let width: Double
    let height: Double

    var maxX: Double { minX + width }
    var maxY: Double { minY + height }
    var centerX: Double { minX + width / 2 }
    var centerY: Double { minY + height / 2 }

    func contains(x: Double, y: Double) -> Bool {
        x >= minX && x <= maxX && y >= minY && y <= maxY
    }
}

nonisolated enum PortraitFollowFrame: Equatable, Sendable {
    case fullSource
    case tracking(NormalizedRect)

    var centerX: Double { crop?.centerX ?? 0.5 }

    var crop: NormalizedRect? {
        if case .tracking(let value) = self { return value }
        return nil
    }
}

nonisolated enum PortraitFollowPlan {
    static let targetAspect = 9.0 / 16.0
    static let minimumConfidence = 0.55
    static let maximumGapSeconds = 1.0

    static func make(track: [AnalysisSpotlightKeyframe], at time: Double) -> PortraitFollowFrame {
        guard let keyframe = interpolated(track: track, at: time),
              keyframe.confidence >= minimumConfidence,
              let crop = crop(for: keyframe) else {
            return .fullSource
        }
        return .tracking(crop)
    }

    private static func interpolated(
        track: [AnalysisSpotlightKeyframe],
        at time: Double
    ) -> AnalysisSpotlightKeyframe? {
        guard time.isFinite else { return nil }
        let keyframes = track
            .filter { $0.timeSeconds.isFinite }
            .sorted { $0.timeSeconds < $1.timeSeconds }
        guard let first = keyframes.first else { return nil }

        guard time >= first.timeSeconds else {
            return time >= first.timeSeconds - maximumGapSeconds && isNormalized(first) ? first : nil
        }
        guard let last = keyframes.last else { return nil }
        guard time <= last.timeSeconds else {
            return time <= last.timeSeconds + maximumGapSeconds && isNormalized(last) ? last : nil
        }

        guard let upperIndex = keyframes.firstIndex(where: { $0.timeSeconds >= time }) else {
            return last
        }
        let upper = keyframes[upperIndex]
        guard upper.timeSeconds != time, upperIndex > keyframes.startIndex else {
            return isNormalized(upper) ? upper : nil
        }
        let lower = keyframes[keyframes.index(before: upperIndex)]
        guard time - lower.timeSeconds <= maximumGapSeconds,
              upper.timeSeconds - time <= maximumGapSeconds,
              isNormalized(lower),
              isNormalized(upper) else {
            return nil
        }
        let progress = (time - lower.timeSeconds) / (upper.timeSeconds - lower.timeSeconds)
        return AnalysisSpotlightKeyframe(
            timeSeconds: time,
            x: interpolate(lower.x, upper.x, progress),
            y: interpolate(lower.y, upper.y, progress),
            width: interpolate(lower.width, upper.width, progress),
            height: interpolate(lower.height, upper.height, progress),
            confidence: interpolate(lower.confidence, upper.confidence, progress)
        )
    }

    private static func crop(for keyframe: AnalysisSpotlightKeyframe) -> NormalizedRect? {
        guard isValid(keyframe),
              keyframe.x >= 0, keyframe.y >= 0,
              keyframe.x + keyframe.width <= 1,
              keyframe.y + keyframe.height <= 1 else {
            return nil
        }

        let horizontalPadding = keyframe.width * 0.2 / 2
        let verticalPadding = keyframe.height * 0.16 / 2
        let paddedMinX = keyframe.x - horizontalPadding
        let paddedMinY = keyframe.y - verticalPadding
        let paddedMaxX = keyframe.x + keyframe.width + horizontalPadding
        let paddedMaxY = keyframe.y + keyframe.height + verticalPadding
        guard paddedMinX >= 0, paddedMinY >= 0, paddedMaxX <= 1, paddedMaxY <= 1 else {
            return nil
        }

        let paddedWidth = paddedMaxX - paddedMinX
        let paddedHeight = paddedMaxY - paddedMinY
        let width = max(paddedWidth, paddedHeight * targetAspect)
        let height = width / targetAspect
        guard width <= 1, height <= 1 else { return nil }

        let centeredMinX = (paddedMinX + paddedMaxX - width) / 2
        let centeredMinY = (paddedMinY + paddedMaxY - height) / 2
        return NormalizedRect(
            minX: min(max(centeredMinX, 0), 1 - width),
            minY: min(max(centeredMinY, 0), 1 - height),
            width: width,
            height: height
        )
    }

    private static func isValid(_ keyframe: AnalysisSpotlightKeyframe) -> Bool {
        [
            keyframe.timeSeconds,
            keyframe.x,
            keyframe.y,
            keyframe.width,
            keyframe.height,
            keyframe.confidence
        ].allSatisfy(\.isFinite) && keyframe.width > 0 && keyframe.height > 0
    }

    private static func isNormalized(_ keyframe: AnalysisSpotlightKeyframe) -> Bool {
        keyframe.x >= 0 && keyframe.y >= 0
            && keyframe.x + keyframe.width <= 1
            && keyframe.y + keyframe.height <= 1
    }

    private static func interpolate(_ lower: Double, _ upper: Double, _ progress: Double) -> Double {
        lower + (upper - lower) * progress
    }
}

nonisolated enum PortraitFollowProjection {
    static func project(_ source: NormalizedRect, in frame: PortraitFollowFrame) -> CGRect? {
        guard isValid(source),
              source.minX >= 0, source.minY >= 0,
              source.maxX <= 1, source.maxY <= 1 else {
            return nil
        }

        guard case .tracking(let crop) = frame else {
            return CGRect(x: source.minX, y: source.minY, width: source.width, height: source.height)
        }
        guard isValid(crop), crop.width > 0, crop.height > 0 else { return nil }

        let minX = (source.minX - crop.minX) / crop.width
        let minY = (source.minY - crop.minY) / crop.height
        let maxX = (source.maxX - crop.minX) / crop.width
        let maxY = (source.maxY - crop.minY) / crop.height
        guard [minX, minY, maxX, maxY].allSatisfy(\.isFinite) else { return nil }
        return CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
    }

    static func project(_ pose: AnalysisPoseFrame, in frame: PortraitFollowFrame) -> CGRect? {
        let points = pose.keypoints.filter { keypoint in
            [keypoint.x, keypoint.y, keypoint.confidence].allSatisfy(\.isFinite)
                && keypoint.x >= 0 && keypoint.x <= 1
                && keypoint.y >= 0 && keypoint.y <= 1
        }
        guard let first = points.first else { return nil }
        let bounds = points.dropFirst().reduce(
            NormalizedRect(minX: first.x, minY: first.y, width: 0, height: 0)
        ) { result, point in
            let minX = min(result.minX, point.x)
            let minY = min(result.minY, point.y)
            let maxX = max(result.maxX, point.x)
            let maxY = max(result.maxY, point.y)
            return NormalizedRect(minX: minX, minY: minY, width: maxX - minX, height: maxY - minY)
        }
        return project(bounds, in: frame)
    }

    private static func isValid(_ rect: NormalizedRect) -> Bool {
        [rect.minX, rect.minY, rect.width, rect.height, rect.maxX, rect.maxY].allSatisfy(\.isFinite)
            && rect.width > 0 && rect.height > 0
    }
}
