import SwiftUI

struct PracticeView: View {
    @EnvironmentObject private var router: AppRouter
    let project: DanceProject
    @State private var currentTime: TimeInterval = 0
    @State private var loopEnabled = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                PracticeStageView(
                    title: project.title,
                    dancerName: project.selectedDancerName ?? "未选择",
                    currentTime: currentTime,
                    isMirrored: project.mirrorEnabled
                )

                Slider(value: $currentTime, in: 0...60)

                HStack {
                    Text(timeLabel(for: currentTime))
                    Spacer()
                    Text("1:00")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 14) {
                    Text("练习控制")
                        .font(.headline)

                    Picker("播放速度", selection: playbackRateBinding) {
                        ForEach(PlaybackRate.allCases) { rate in
                            Text(rate.title).tag(rate.rawValue)
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

                    ForEach(DanceProject.sampleTimelineNodes) { node in
                        Button {
                            currentTime = node.time
                            touch()
                        } label: {
                            TimelineNodeRow(node: node)
                        }
                        .buttonStyle(.plain)
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
            if project.phase == .readyToPractice {
                project.phase = .practicing
                touch()
            }
        }
        .navigationTitle("练习")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func touch() {
        project.updatedAt = Date()
    }

    private var mirrorBinding: Binding<Bool> {
        Binding {
            project.mirrorEnabled
        } set: { newValue in
            project.mirrorEnabled = newValue
            touch()
        }
    }

    private var playbackRateBinding: Binding<Double> {
        Binding {
            project.defaultPlaybackRate
        } set: { newValue in
            project.defaultPlaybackRate = newValue
            touch()
        }
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
    let title: String
    let dancerName: String
    let currentTime: TimeInterval
    let isMirrored: Bool

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 8)
                .fill(
                    LinearGradient(
                        colors: [.black, .indigo.opacity(0.75), .teal.opacity(0.5)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )

            HStack(alignment: .bottom, spacing: 22) {
                ForEach(0..<5) { index in
                    Image(systemName: index == 2 ? "figure.dance" : "figure.stand")
                        .font(.system(size: index == 2 ? 52 : 36))
                        .foregroundStyle(index == 2 ? .yellow : .white.opacity(0.7))
                        .padding(.bottom, index == 2 ? 34 : 14)
                }
            }
            .frame(maxWidth: .infinity)
            .scaleEffect(x: isMirrored ? -1 : 1, y: 1)

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                Text("目标：\(dancerName) · \(timeLabel)")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.85))
            }
            .foregroundStyle(.white)
            .padding(12)
        }
        .frame(height: 230)
        .accessibilityLabel("练习视频预览")
    }

    private var timeLabel: String {
        let minutes = Int(currentTime) / 60
        let seconds = Int(currentTime) % 60
        return String(format: "%d:%02d", minutes, seconds)
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
