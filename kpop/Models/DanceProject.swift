import Foundation
import SwiftData

enum ProjectPhase: String, Codable, CaseIterable {
    case created
    case analyzing
    case needsDancerSelection
    case readyToPractice
    case practicing
    case failed
}

extension ProjectPhase {
    var title: String {
        switch self {
        case .created: "已创建"
        case .analyzing: "分析中"
        case .needsDancerSelection: "待选舞者"
        case .readyToPractice: "可练习"
        case .practicing: "练习中"
        case .failed: "分析失败"
        }
    }

    var systemImage: String {
        switch self {
        case .created: "doc.badge.plus"
        case .analyzing: "waveform.path.ecg"
        case .needsDancerSelection: "figure.dance"
        case .readyToPractice: "play.circle"
        case .practicing: "repeat.circle"
        case .failed: "exclamationmark.triangle"
        }
    }
}

enum PlaybackRate: Double, CaseIterable, Identifiable {
    case half = 0.5
    case threeQuarter = 0.75
    case normal = 1.0

    var id: Double { rawValue }

    var title: String {
        switch self {
        case .half: "0.5x"
        case .threeQuarter: "0.75x"
        case .normal: "1x"
        }
    }
}

enum DanceNodeKind: String, CaseIterable, Identifiable {
    case beat
    case keyAction
    case transition

    var id: String { rawValue }

    var title: String {
        switch self {
        case .beat: "Beat"
        case .keyAction: "Key"
        case .transition: "Move"
        }
    }
}

struct DanceTimelineNode: Identifiable, Hashable {
    let id = UUID()
    let time: TimeInterval
    let kind: DanceNodeKind
    let label: String
    let isHard: Bool

    var timeLabel: String {
        let minutes = Int(time) / 60
        let seconds = Int(time) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

struct AnalysisStep: Identifiable {
    let id = UUID()
    let title: String
    let detail: String
    let systemImage: String
}

struct DancerOption: Identifiable, Hashable {
    let id: Int
    let name: String
    let position: String
}

@Model
final class DanceProject {
    @Attribute(.unique) var id: UUID
    var createdAt: Date
    var updatedAt: Date

    var title: String
    var sourceVideoName: String
    var sourceVideoPath: String?
    var videoDuration: Double = 0
    var selectedDancerName: String?
    var mirrorEnabled: Bool
    var defaultPlaybackRate: Double

    var sourceFingerprint: String = ""
    var remoteJobId: String?
    var remoteUploadId: String?
    var confirmedUploadOffset: Int64?
    var uploadExpiresAt: Date?
    var analysisSchemaVersion: Int?
    var analysisPackageRelativePath: String?
    var lastPracticedAt: Date?

    var phaseRawValue: String

    init(
        id: UUID = UUID(),
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        title: String,
        sourceVideoName: String = "本地视频",
        sourceVideoPath: String? = nil,
        videoDuration: Double = 0,
        selectedDancerName: String? = nil,
        mirrorEnabled: Bool = false,
        defaultPlaybackRate: Double = 1.0,
        phase: ProjectPhase = .created
    ) {
        self.id = id
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.title = title
        self.sourceVideoName = sourceVideoName
        self.sourceVideoPath = sourceVideoPath
        self.videoDuration = videoDuration
        self.selectedDancerName = selectedDancerName
        self.mirrorEnabled = mirrorEnabled
        self.defaultPlaybackRate = defaultPlaybackRate
        self.phaseRawValue = phase.rawValue
    }

    var phase: ProjectPhase {
        get { ProjectPhase(rawValue: phaseRawValue) ?? .created }
        set { phaseRawValue = newValue.rawValue }
    }

    var playbackRate: PlaybackRate {
        get { PlaybackRate(rawValue: defaultPlaybackRate) ?? .normal }
        set { defaultPlaybackRate = newValue.rawValue }
    }
}

extension DanceProject {
    static let sampleTimelineNodes: [DanceTimelineNode] = [
        DanceTimelineNode(time: 4, kind: .beat, label: "Intro 1", isHard: false),
        DanceTimelineNode(time: 12, kind: .keyAction, label: "肩部定点", isHard: false),
        DanceTimelineNode(time: 19, kind: .transition, label: "左移换位", isHard: true),
        DanceTimelineNode(time: 28, kind: .keyAction, label: "手部快速组合", isHard: true),
        DanceTimelineNode(time: 42, kind: .beat, label: "副歌入口", isHard: false)
    ]

    static let analysisSteps: [AnalysisStep] = [
        AnalysisStep(title: "抽取视频帧", detail: "读取固定机位视频中的关键帧。", systemImage: "film.stack"),
        AnalysisStep(title: "人体姿态识别", detail: "使用 Vision framework 提取身体关键点。", systemImage: "figure.stand"),
        AnalysisStep(title: "节拍检测", detail: "估算 BPM 并生成 beat nodes。", systemImage: "metronome"),
        AnalysisStep(title: "动作节点生成", detail: "识别关键动作、过渡动作和高难片段。", systemImage: "point.topleft.down.curvedto.point.bottomright.up")
    ]

    static let dancerOptions: [DancerOption] = [
        DancerOption(id: 1, name: "Dancer 1", position: "左侧前排"),
        DancerOption(id: 2, name: "Dancer 2", position: "中间主位"),
        DancerOption(id: 3, name: "Dancer 3", position: "右侧前排"),
        DancerOption(id: 4, name: "Dancer 4", position: "后排移动位")
    ]
}
