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

nonisolated enum PracticeFollowStatus: Equatable, Sendable {
    case tracking
    case fullFrameFallback
    case unavailable
}

nonisolated struct PracticeFollowPresentation: Equatable, Sendable {
    let frame: PortraitFollowFrame

    var status: PracticeFollowStatus {
        switch frame {
        case .tracking:
            .tracking
        case .fullSource:
            .fullFrameFallback
        }
    }
}

nonisolated enum PracticeOverlayProjection {
    static func project(
        _ source: NormalizedRect,
        in frame: PortraitFollowFrame,
        sourceAspectRatio: Double,
        canvasSize: CGSize
    ) -> CGRect? {
        guard sourceAspectRatio.isFinite,
              sourceAspectRatio > 0,
              canvasSize.width.isFinite,
              canvasSize.height.isFinite,
              canvasSize.width > 0,
              canvasSize.height > 0,
              let normalized = PortraitFollowProjection.project(source, in: frame) else {
            return nil
        }

        let contentRect = contentRect(
            for: frame,
            sourceAspectRatio: sourceAspectRatio,
            canvasSize: canvasSize
        )

        return CGRect(
            x: contentRect.minX + normalized.minX * contentRect.width,
            y: contentRect.minY + normalized.minY * contentRect.height,
            width: normalized.width * contentRect.width,
            height: normalized.height * contentRect.height
        )
    }

    static func project(
        _ source: CGPoint,
        in frame: PortraitFollowFrame,
        sourceAspectRatio: Double,
        canvasSize: CGSize
    ) -> CGPoint? {
        guard source.x.isFinite,
              source.y.isFinite,
              source.x >= 0,
              source.y >= 0,
              source.x <= 1,
              source.y <= 1,
              sourceAspectRatio.isFinite,
              sourceAspectRatio > 0,
              canvasSize.width.isFinite,
              canvasSize.height.isFinite,
              canvasSize.width > 0,
              canvasSize.height > 0 else {
            return nil
        }

        let normalized: CGPoint
        switch frame {
        case .fullSource:
            normalized = source
        case .tracking(let crop):
            guard crop.width.isFinite,
                  crop.height.isFinite,
                  crop.width > 0,
                  crop.height > 0 else {
                return nil
            }
            normalized = CGPoint(
                x: (source.x - crop.minX) / crop.width,
                y: (source.y - crop.minY) / crop.height
            )
        }
        let contentRect = contentRect(
            for: frame,
            sourceAspectRatio: sourceAspectRatio,
            canvasSize: canvasSize
        )
        return CGPoint(
            x: contentRect.minX + normalized.x * contentRect.width,
            y: contentRect.minY + normalized.y * contentRect.height
        )
    }

    private static func contentRect(
        for frame: PortraitFollowFrame,
        sourceAspectRatio: Double,
        canvasSize: CGSize
    ) -> CGRect {
        guard case .fullSource = frame else {
            return CGRect(origin: .zero, size: canvasSize)
        }

        let canvasAspectRatio = canvasSize.width / canvasSize.height
        if sourceAspectRatio > canvasAspectRatio {
            let height = canvasSize.width / sourceAspectRatio
            return CGRect(
                x: 0,
                y: (canvasSize.height - height) / 2,
                width: canvasSize.width,
                height: height
            )
        }
        let width = canvasSize.height * sourceAspectRatio
        return CGRect(
            x: (canvasSize.width - width) / 2,
            y: 0,
            width: width,
            height: canvasSize.height
        )
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
        isValid(keyframe)
            && keyframe.x >= 0 && keyframe.y >= 0
            && keyframe.x + keyframe.width <= 1
            && keyframe.y + keyframe.height <= 1
    }

    private static func interpolate(_ lower: Double, _ upper: Double, _ progress: Double) -> Double {
        lower + (upper - lower) * progress
    }
}

nonisolated enum MemberFancamPlan {
    private static let minimumPointConfidence = 0.5
    private static let maximumGapSeconds = 1.0
    private static let targetAspect = 9.0 / 16.0

    static func make(track: [AnalysisPoseFrame], at time: Double) -> PortraitFollowFrame {
        guard let crop = interpolatedFullBodyCrop(track: track, at: time) else {
            return .fullSource
        }
        return .tracking(crop)
    }

    static func fullBodyCrop(for frame: AnalysisPoseFrame) -> NormalizedRect? {
        let points = Dictionary(uniqueKeysWithValues: frame.keypoints.map { ($0.name, $0) })
        guard let head = points["nose"],
              let leftAnkle = points["left_ankle"],
              let rightAnkle = points["right_ankle"],
              [head, leftAnkle, rightAnkle].allSatisfy(isReliable) else {
            return nil
        }
        let visible = frame.keypoints.filter(isReliable)
        guard let first = visible.first else { return nil }
        let bounds = visible.dropFirst().reduce(
            (minX: first.x, minY: first.y, maxX: first.x, maxY: first.y)
        ) { result, point in
            (min(result.minX, point.x), min(result.minY, point.y), max(result.maxX, point.x), max(result.maxY, point.y))
        }
        let paddedWidth = max(0.12, (bounds.maxX - bounds.minX) * 1.5)
        let paddedHeight = max(0.24, (bounds.maxY - bounds.minY) * 1.18)
        let width = max(paddedWidth, paddedHeight * targetAspect)
        let height = width / targetAspect
        guard width <= 1, height <= 1 else { return nil }
        let centerX = (bounds.minX + bounds.maxX) / 2
        let centerY = (bounds.minY + bounds.maxY) / 2
        return NormalizedRect(
            minX: min(max(centerX - width / 2, 0), 1 - width),
            minY: min(max(centerY - height / 2, 0), 1 - height),
            width: width,
            height: height
        )
    }

    private static func interpolatedFullBodyCrop(
        track: [AnalysisPoseFrame],
        at time: Double
    ) -> NormalizedRect? {
        guard time.isFinite else { return nil }
        let crops = track.compactMap { frame -> (time: Double, crop: NormalizedRect)? in
            guard frame.timeSeconds.isFinite, let crop = fullBodyCrop(for: frame) else { return nil }
            return (frame.timeSeconds, crop)
        }.sorted { $0.time < $1.time }
        guard let first = crops.first else { return nil }
        if time <= first.time {
            return first.time - time <= maximumGapSeconds ? first.crop : nil
        }
        guard let last = crops.last else { return nil }
        if time >= last.time {
            return time - last.time <= maximumGapSeconds ? last.crop : nil
        }
        guard let upperIndex = crops.firstIndex(where: { $0.time >= time }) else { return nil }
        let upper = crops[upperIndex]
        guard upper.time != time, upperIndex > crops.startIndex else { return upper.crop }
        let lower = crops[crops.index(before: upperIndex)]
        guard time - lower.time <= maximumGapSeconds,
              upper.time - time <= maximumGapSeconds else {
            return time - lower.time <= maximumGapSeconds ? lower.crop : nil
        }
        let progress = (time - lower.time) / (upper.time - lower.time)
        return NormalizedRect(
            minX: interpolate(lower.crop.minX, upper.crop.minX, progress),
            minY: interpolate(lower.crop.minY, upper.crop.minY, progress),
            width: interpolate(lower.crop.width, upper.crop.width, progress),
            height: interpolate(lower.crop.height, upper.crop.height, progress)
        )
    }

    private static func interpolate(_ lower: Double, _ upper: Double, _ progress: Double) -> Double {
        lower + (upper - lower) * progress
    }

    private static func isReliable(_ point: AnalysisPoseKeypoint) -> Bool {
        point.confidence >= minimumPointConfidence
            && point.x.isFinite && point.y.isFinite
            && (0...1).contains(point.x) && (0...1).contains(point.y)
    }
}

nonisolated struct PracticeSkeletonSegment: Equatable, Sendable {
    let from: String
    let to: String
}

nonisolated enum PracticeSkeleton {
    private static let topology = [
        PracticeSkeletonSegment(from: "nose", to: "left_shoulder"),
        PracticeSkeletonSegment(from: "nose", to: "right_shoulder"),
        PracticeSkeletonSegment(from: "left_shoulder", to: "right_shoulder"),
        PracticeSkeletonSegment(from: "left_shoulder", to: "left_elbow"),
        PracticeSkeletonSegment(from: "left_elbow", to: "left_wrist"),
        PracticeSkeletonSegment(from: "right_shoulder", to: "right_elbow"),
        PracticeSkeletonSegment(from: "right_elbow", to: "right_wrist"),
        PracticeSkeletonSegment(from: "left_shoulder", to: "left_hip"),
        PracticeSkeletonSegment(from: "right_shoulder", to: "right_hip"),
        PracticeSkeletonSegment(from: "left_hip", to: "right_hip"),
        PracticeSkeletonSegment(from: "left_hip", to: "left_knee"),
        PracticeSkeletonSegment(from: "left_knee", to: "left_ankle"),
        PracticeSkeletonSegment(from: "right_hip", to: "right_knee"),
        PracticeSkeletonSegment(from: "right_knee", to: "right_ankle")
    ]

    static func segments(for points: [AnalysisPoseKeypoint]) -> [PracticeSkeletonSegment] {
        let names = Set(points.filter { $0.confidence >= 0.5 }.map(\.name))
        return topology.filter { names.contains($0.from) && names.contains($0.to) }
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
