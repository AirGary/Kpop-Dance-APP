import AVFoundation
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
            VStack(alignment: .leading, spacing: 18) {
                if let player {
                    PracticeStageView(
                        player: player,
                        title: project.title,
                        dancerName: project.selectedDancerName ?? "未选择",
                        currentTime: currentTime,
                        isMirrored: project.mirrorEnabled,
                        isPlaying: isPlaying,
                        onTogglePlayback: togglePlayback
                    )
                } else {
                    PracticeUnavailableView(sourceVideoName: project.sourceVideoName)
                }

                Slider(value: playbackTimeBinding, in: 0...safeDuration)
                    .disabled(player == nil)

                HStack {
                    Text(timeLabel(for: currentTime))
                    Spacer()
                    Text(timeLabel(for: safeDuration))
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 14) {
                    Text("练习控制")
                        .font(.headline)

                    Button {
                        togglePlayback()
                    } label: {
                        Label(isPlaying ? "暂停" : "播放", systemImage: isPlaying ? "pause.fill" : "play.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(player == nil)

                    Picker("播放速度", selection: playbackRateBinding) {
                        ForEach(PlaybackRate.allCases) { rate in
                            Text(rate.title).tag(rate)
                        }
                    }
                    .pickerStyle(.segmented)

                    Toggle("镜像模式", isOn: mirrorBinding)
                    Toggle("片段循环", isOn: $loopEnabled)

                    HStack(spacing: 10) {
                        ControlChip(title: "Beat", icon: "metronome", color: AppUI.cyan)
                        ControlChip(title: loopEnabled ? "Loop On" : "Loop Off", icon: "repeat", color: loopEnabled ? AppUI.violet : .secondary)
                        ControlChip(title: project.mirrorEnabled ? "Mirror" : "Normal", icon: "rectangle.triangle.2.outward", color: project.mirrorEnabled ? AppUI.coral : .secondary)
                    }
                }
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 12) {
                    Text("时间轴节点")
                        .font(.headline)

                    ForEach(visibleTimelineNodes) { node in
                        Button {
                            seek(to: node.time)
                        } label: {
                            TimelineNodeRow(node: node)
                        }
                        .buttonStyle(.plain)
                        .disabled(player == nil)
                    }
                }
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 12) {
                    Label("换位提示", systemImage: "point.topleft.down.curvedto.point.bottomright.up")
                        .font(.headline)

                    Text("当前目标舞者保持中间主位，下一段向左侧前排移动。")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Button {
                        router.popToRoot()
                    } label: {
                        Label("返回首页", systemImage: "house")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                .padding(16)
                .cardBackground()
            }
            .padding(18)
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
            .padding(.vertical, 9)
            .background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct PracticeStageView: View {
    let player: AVPlayer
    let title: String
    let dancerName: String
    let currentTime: TimeInterval
    let isMirrored: Bool
    let isPlaying: Bool
    let onTogglePlayback: () -> Void

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            PracticePlayerView(player: player, isMirrored: isMirrored)

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                Text("目标：\(dancerName) · \(timeLabel)")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.85))
            }
            .foregroundStyle(.white)
            .padding(12)

            VStack {
                HStack {
                    Spacer()

                    Button(action: onTogglePlayback) {
                        Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(12)
                            .background(.black.opacity(0.45), in: Circle())
                    }
                    .buttonStyle(.plain)
                    .padding(12)
                }

                Spacer()
            }
        }
        .frame(height: 230)
        .background(.black, in: RoundedRectangle(cornerRadius: 8))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .accessibilityLabel("练习视频预览")
    }

    private var timeLabel: String {
        let minutes = Int(currentTime) / 60
        let seconds = Int(currentTime) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

private struct PracticeUnavailableView: View {
    let sourceVideoName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("练习视频不可用", systemImage: "exclamationmark.triangle")
                .font(.headline)
                .foregroundStyle(AppUI.coral)

            Text("未找到可播放的本地视频文件：\(sourceVideoName)")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 230, alignment: .leading)
        .padding(16)
        .cardBackground()
    }
}

private struct TimelineNodeRow: View {
    let node: DanceTimelineNode

    var body: some View {
        HStack(spacing: 12) {
            Text(node.kind.title)
                .font(.caption.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 44, height: 28)
                .background(nodeColor, in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 3) {
                Text(node.label)
                    .font(.subheadline.weight(.semibold))
                Text(node.timeLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if node.isHard {
                Label("难点", systemImage: "flame.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
        .padding(.vertical, 4)
    }

    private var nodeColor: Color {
        switch node.kind {
        case .beat: .blue
        case .keyAction: .purple
        case .transition: .teal
        }
    }
}
