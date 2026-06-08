import SwiftUI

struct DancerPickView: View {
    @EnvironmentObject private var router: AppRouter
    let project: DanceProject
    @State private var selectedDancer: DancerOption?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DancerPreview(selectedDancer: selectedDancer)

                VStack(alignment: .leading, spacing: 12) {
                    Text("选择目标舞者")
                        .font(.headline)

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(DanceProject.dancerOptions) { dancer in
                            DancerOptionCard(
                                dancer: dancer,
                                isSelected: selectedDancer == dancer
                            ) {
                                selectedDancer = dancer
                            }
                        }
                    }
                }
                .padding(16)
                .cardBackground()

                VStack(spacing: 10) {
                    Button {
                        guard let selectedDancer else { return }
                        project.selectedDancerName = selectedDancer.name
                        project.phase = .readyToPractice
                        project.updatedAt = Date()
                        router.replaceTop(with: .practice(projectId: project.id))
                    } label: {
                        Label("生成练习时间轴", systemImage: "timeline.selection")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedDancer == nil)

                    Button {
                        project.phase = .analyzing
                        project.updatedAt = Date()
                        router.replaceTop(with: .analysis(projectId: project.id))
                    } label: {
                        Label("重新检测", systemImage: "arrow.clockwise")
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
        .navigationTitle("选择舞者")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct DancerPreview: View {
    let selectedDancer: DancerOption?

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(
                    LinearGradient(
                        colors: [.black.opacity(0.88), .blue.opacity(0.45)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            HStack(alignment: .bottom, spacing: 16) {
                ForEach(DanceProject.dancerOptions) { dancer in
                    VStack(spacing: 6) {
                        Image(systemName: "figure.dance")
                            .font(.system(size: selectedDancer == dancer ? 38 : 30))
                        Text("\(dancer.id)")
                            .font(.caption.weight(.bold))
                    }
                    .foregroundStyle(selectedDancer == dancer ? .yellow : .white.opacity(0.75))
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, dancer.id == 2 ? 28 : 12)
                }
            }
            .padding(.horizontal, 18)
        }
        .frame(height: 190)
        .cardBackground()
        .accessibilityLabel("舞者检测预览")
    }
}

private struct DancerOptionCard: View {
    let dancer: DancerOption
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("\(dancer.id)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 26, height: 26)
                        .background(isSelected ? AppUI.violet : Color.secondary, in: Circle())

                    Spacer()

                    if isSelected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                }

                Text(dancer.name)
                    .font(.headline)
                    .foregroundStyle(AppUI.ink)

                Text(dancer.position)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? AppUI.violet.opacity(0.1) : .white, in: RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? AppUI.violet : Color.black.opacity(0.06), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
