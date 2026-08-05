import SwiftUI
import UIKit

struct IdentityConfirmationView: View {
    let confirmation: IdentityConfirmation
    let client: AnalysisAPIClient?
    let jobID: UUID?
    let submit: (IdentityDecisionValue) async -> Bool

    @State private var submitting = false
    @State private var submissionError: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    StageSectionHeader(
                        eyebrow: "IDENTITY CHECK",
                        title: "是否仍是所选舞者？",
                        detail: "确认后会从此片段继续分析；选择“不是”将保留该时段的完整画面。"
                    )
                    HStack(spacing: 12) {
                        ConfirmationImage(client: client, jobID: jobID, path: confirmation.previousImagePath)
                            .accessibilityLabel("确认前一片段")
                        ConfirmationImage(client: client, jobID: jobID, path: confirmation.candidateImagePath)
                            .accessibilityLabel("确认候选片段")
                    }
                    .frame(height: 210)
                    HStack {
                        Text(timeRange(confirmation.previousInterval)).frame(maxWidth: .infinity, alignment: .leading)
                        Text(timeRange(confirmation.candidateInterval)).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(AppUI.inkSoft)

                    VStack(spacing: 12) {
                        Button {
                            send(.same)
                        } label: {
                            Label("是，同一位舞者", systemImage: "checkmark.circle.fill").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("identity-confirmation-same")

                        Button {
                            send(.different)
                        } label: {
                            Label("不是", systemImage: "rectangle.slash").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("identity-confirmation-different")
                    }
                    .disabled(submitting)
                    if let submissionError {
                        Label(submissionError, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
                .padding(20)
            }
            .background(AppUI.background)
            .navigationTitle("身份确认")
            .navigationBarTitleDisplayMode(.inline)
        }
        .interactiveDismissDisabled()
    }

    private func timeRange(_ interval: CandidateAppearanceInterval) -> String {
        String(format: "%.1fs – %.1fs", interval.startSeconds, interval.endSeconds)
    }

    private func send(_ decision: IdentityDecisionValue) {
        submitting = true
        submissionError = nil
        Task {
            if !(await submit(decision)) {
                submitting = false
                submissionError = "提交失败，请重试。"
            }
        }
    }
}

private struct ConfirmationImage: View {
    let client: AnalysisAPIClient?
    let jobID: UUID?
    let path: String
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image { Image(uiImage: image).resizable().scaledToFill() }
            else { ContentUnavailableView("图片不可用", systemImage: "photo") }
        }
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .task(id: "\(jobID?.uuidString ?? "")-\(path)") {
            guard let client, let jobID, let data = try? await client.downloadContent(jobID: jobID, relativePath: path) else { return }
            image = UIImage(data: data)
        }
    }
}
