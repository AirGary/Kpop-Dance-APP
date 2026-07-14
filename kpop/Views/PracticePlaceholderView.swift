import AVFoundation
import SwiftData
import SwiftUI

struct PracticeView: View {
    @EnvironmentObject private var router: AppRouter
    let project: DanceProject
    @State private var player: AVPlayer?
    @State private var duration: Double = 0
    @State private var isPlaying = false
    @State private var timeObserverToken: Any?
    @State private var currentTime: TimeInterval = 0
    @State private var loopEnabled = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Practice",
                        title: project.title,
                        detail: "围绕播放器集中练习当前片段，使用速度、镜像和节点跳转快速回放难点动作。"
                    )

                    if let player {
                        PracticeStageView(
                            player: player,
                            title: project.title,
                            dancerName: project.selectedDancerName ?? "未选择",
                            currentTime: currentTime,
                            totalDuration: safeDuration,
                            isMirrored: project.mirrorEnabled,
                            isPlaying: isPlaying,
                            playbackRateTitle: project.playbackRate.title,
                            onTogglePlayback: togglePlayback
                        )
                    } else {
                        PracticeUnavailableView(sourceVideoName: project.sourceVideoName)
                    }
                }

                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Transport",
                        title: "播放器控制",
                        detail: "拖动进度条快速定位，速度和镜像会直接作用于当前练习视频。"
                    )

                    Slider(value: playbackTimeBinding, in: 0...safeDuration)
                        .tint(AppUI.violet)
                        .disabled(player == nil)

                    HStack {
                        Text("当前 \(timeLabel(for: currentTime))")
                        Spacer()
                        Text("总时长 \(timeLabel(for: safeDuration))")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppUI.inkSoft)

                    HStack(spacing: 12) {
                        Button {
                            togglePlayback()
                        } label: {
                            Label(isPlaying ? "暂停练习" : "开始练习", systemImage: isPlaying ? "pause.fill" : "play.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(player == nil)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("当前速度")
                                .font(.caption)
                                .foregroundStyle(AppUI.inkSoft)
                            Text(project.playbackRate.title)
                                .font(.headline.weight(.bold))
                                .foregroundStyle(AppUI.ink)
                        }
                        .frame(width: 90, alignment: .leading)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .cardBackground(.muted)
                    }

                    Picker("播放速度", selection: playbackRateBinding) {
                        ForEach(PlaybackRate.allCases) { rate in
                            Text(rate.title).tag(rate)
                        }
                    }
                    .pickerStyle(.segmented)
                    .disabled(player == nil)

                    HStack(spacing: 12) {
                        ToggleCard(
                            title: "镜像模式",
                            detail: "适合照镜子跟练",
                            systemImage: "rectangle.leadinghalf.filled",
                            isOn: mirrorBinding
                        )
                        .disabled(player == nil)

                        ToggleCard(
                            title: "片段循环",
                            detail: "结尾自动回到开头",
                            systemImage: "repeat",
                            isOn: $loopEnabled
                        )
                        .disabled(player == nil)
                    }

                    HStack(spacing: 10) {
                        ControlChip(title: "Beat", icon: "metronome", color: AppUI.cyan)
                        ControlChip(title: loopEnabled ? "Loop On" : "Loop Off", icon: "repeat", color: loopEnabled ? AppUI.violet : .secondary)
                        ControlChip(title: project.mirrorEnabled ? "Mirror" : "Normal", icon: "rectangle.triangle.2.outward", color: project.mirrorEnabled ? AppUI.coral : .secondary)
                    }
                }
                .padding(AppUI.panelPadding)
                .cardBackground(.primary)
                .opacity(player == nil ? 0.78 : 1)

                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Timeline",
                        title: "动作节点",
                        detail: "点击任意节点跳转到对应时间点，优先重复练习关键动作和高难片段。"
                    )

                    ForEach(visibleTimelineNodes) { node in
                        Button {
                            seek(to: node.time)
                        } label: {
                            TimelineNodeRow(node: node, isActive: isNodeActive(node))
                        }
                        .buttonStyle(.plain)
                        .disabled(player == nil)
                    }
                }
                .padding(AppUI.panelPadding)
                .cardBackground(.primary)

                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Formation",
                        title: "换位提示",
                        detail: "当前目标舞者保持中间主位，下一段向左侧前排移动。"
                    )

                    Button {
                        router.popToRoot()
                    } label: {
                        Label("返回首页", systemImage: "house")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                .padding(AppUI.panelPadding)
                .cardBackground(.muted)
            }
            .padding(20)
        }
        .background(AppUI.background)
        .onAppear {
            preparePlayer()
            if project.phase == .readyToPractice {
                project.phase = .practicing
                touch()
            }
        }
        .onDisappear {
            cleanupPlayer()
        }
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime)) { notification in
            guard
                let currentItem = player?.currentItem,
                notification.object as? AVPlayerItem === currentItem
            else {
                return
            }

            if loopEnabled {
                seek(to: 0)
                player?.play()
                player?.rate = Float(project.playbackRate.rawValue)
                isPlaying = true
            } else {
                isPlaying = false
                currentTime = safeDuration
            }
        }
        .navigationTitle("练习")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func touch() {
        project.updatedAt = Date()
    }

    private var safeDuration: Double {
        max(duration, 1)
    }

    private var visibleTimelineNodes: [DanceTimelineNode] {
        DanceProject.sampleTimelineNodes.filter { $0.time <= safeDuration }
    }

    private var mirrorBinding: Binding<Bool> {
        Binding {
            project.mirrorEnabled
        } set: { newValue in
            project.mirrorEnabled = newValue
            touch()
        }
    }

    private var playbackRateBinding: Binding<PlaybackRate> {
        Binding {
            project.playbackRate
        } set: { newValue in
            project.playbackRate = newValue
            if isPlaying {
                player?.rate = Float(newValue.rawValue)
            }
            touch()
        }
    }

    private var playbackTimeBinding: Binding<Double> {
        Binding {
            currentTime
        } set: { newValue in
            seek(to: newValue)
        }
    }

    private func preparePlayer() {
        cleanupPlayer()

        guard
            let path = project.sourceVideoPath,
            FileManager.default.fileExists(atPath: path)
        else {
            duration = max(project.videoDuration, 1)
            currentTime = 0
            return
        }

        let player = AVPlayer(url: URL(fileURLWithPath: path))
        self.player = player
        duration = max(project.videoDuration, 1)
        currentTime = min(currentTime, safeDuration)
        addTimeObserver(to: player)
    }

    private func cleanupPlayer() {
        if let timeObserverToken, let player {
            player.removeTimeObserver(timeObserverToken)
        }
        player?.pause()
        player = nil
        timeObserverToken = nil
        isPlaying = false
    }

    private func addTimeObserver(to player: AVPlayer) {
        let interval = CMTime(seconds: 0.25, preferredTimescale: 600)
        timeObserverToken = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { time in
            currentTime = min(max(time.seconds, 0), safeDuration)
        }
    }

    private func togglePlayback() {
        guard let player else { return }

        if isPlaying {
            player.pause()
        } else {
            if currentTime >= safeDuration {
                seek(to: 0)
            }
            player.play()
            player.rate = Float(project.playbackRate.rawValue)
        }

        isPlaying.toggle()
        touch()
    }

    private func seek(to time: Double) {
        let clampedTime = min(max(time, 0), safeDuration)
        currentTime = clampedTime

        guard let player else { return }

        let target = CMTime(seconds: clampedTime, preferredTimescale: 600)
        player.seek(to: target)
        touch()
    }

    private func isNodeActive(_ node: DanceTimelineNode) -> Bool {
        abs(currentTime - node.time) < 3
    }

    private func timeLabel(for time: TimeInterval) -> String {
        let minutes = Int(time) / 60
        let seconds = Int(time) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

private struct ControlChip: View {
    let title: String
    let icon: String
    let color: Color

    var body: some View {
        Label(title, systemImage: icon)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct ToggleCard: View {
    let title: String
    let detail: String
    let systemImage: String
    @Binding var isOn: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(AppUI.violet)
                    .frame(width: 34, height: 34)
                    .background(AppUI.violet.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                Spacer()

                Toggle("", isOn: $isOn)
                    .labelsHidden()
            }

            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppUI.ink)

            Text(detail)
                .font(.caption)
                .foregroundStyle(AppUI.inkSoft)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .cardBackground(.muted)
    }
}

private struct PracticeStageView: View {
    let player: AVPlayer
    let title: String
    let dancerName: String
    let currentTime: TimeInterval
    let totalDuration: TimeInterval
    let isMirrored: Bool
    let isPlaying: Bool
    let playbackRateTitle: String
    let onTogglePlayback: () -> Void

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            PracticePlayerView(player: player, isMirrored: isMirrored)

            LinearGradient(
                colors: [.black.opacity(0.55), .clear, .black.opacity(0.72)],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    StatusBadge(text: playbackRateTitle, systemImage: "speedometer", color: .white)
                    Spacer()
                    StatusBadge(text: isMirrored ? "镜像中" : "正常方向", systemImage: "rectangle.triangle.2.outward", color: .white)
                }

                Spacer()

                VStack(alignment: .leading, spacing: 8) {
                    Text(title)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.white)
                    Text("目标：\(dancerName)")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.84))
                    Text("\(timeLabel(currentTime)) / \(timeLabel(totalDuration))")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding(18)

            VStack {
                HStack {
                    Spacer()

                    Button(action: onTogglePlayback) {
                        Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                            .font(.title2.weight(.bold))
                            .foregroundStyle(AppUI.ink)
                            .frame(width: 56, height: 56)
                            .background(.white, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .padding(18)
                }

                Spacer()
            }
        }
        .frame(height: 300)
        .background(.black, in: RoundedRectangle(cornerRadius: 30, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .stroke(.white.opacity(0.08), lineWidth: 1)
        )
        .accessibilityLabel("练习视频预览")
    }

    private func timeLabel(_ time: TimeInterval) -> String {
        let minutes = Int(time) / 60
        let seconds = Int(time) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

private struct PracticeUnavailableView: View {
    let sourceVideoName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.title2)
                    .foregroundStyle(AppUI.coral)
                    .frame(width: 48, height: 48)
                    .background(AppUI.coral.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("视频不可用")
                        .font(.headline)
                        .foregroundStyle(AppUI.ink)
                    Text("未找到可播放的本地视频文件：\(sourceVideoName)")
                        .font(.subheadline)
                        .foregroundStyle(AppUI.inkSoft)
                }
            }

            Text("请返回导入页重新选择本地视频后再继续练习。")
                .font(.subheadline)
                .foregroundStyle(AppUI.inkSoft)
        }
        .frame(maxWidth: .infinity, minHeight: 300, alignment: .leading)
        .padding(20)
        .cardBackground(.muted)
    }
}

private struct TimelineNodeRow: View {
    let node: DanceTimelineNode
    let isActive: Bool

    var body: some View {
        HStack(spacing: 14) {
            VStack(spacing: 6) {
                Circle()
                    .fill(isActive ? nodeColor : nodeColor.opacity(0.25))
                    .frame(width: 12, height: 12)

                Rectangle()
                    .fill(AppUI.divider)
                    .frame(width: 2, height: 44)
                    .opacity(node.isHard ? 0.8 : 0.35)
            }

            Text(node.kind.title)
                .font(.caption.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 52, height: 30)
                .background(nodeColor, in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            VStack(alignment: .leading, spacing: 4) {
                Text(node.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppUI.ink)
                Text(node.timeLabel)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }

            Spacer()

            if node.isHard {
                Label("难点", systemImage: "flame.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppUI.coral)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 2)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(isActive ? nodeColor.opacity(0.1) : .clear)
        )
    }

    private var nodeColor: Color {
        switch node.kind {
        case .beat: AppUI.cyan
        case .keyAction: AppUI.violet
        case .transition: AppUI.lime
        }
    }
}

#Preview("Practice Screen") {
    NavigationStack {
        PracticeView(
            project: {
                let project = DanceProject(
                    title: "XG - GALA",
                    sourceVideoName: "Preview Video",
                    videoDuration: 76,
                    selectedDancerName: "Dancer 2",
                    defaultPlaybackRate: PlaybackRate.threeQuarter.rawValue,
                    phase: .practicing
                )
                project.mirrorEnabled = true
                return project
            }()
        )
        .environmentObject(AppRouter())
    }
    .modelContainer(PreviewProjects.previewContainer())
}
