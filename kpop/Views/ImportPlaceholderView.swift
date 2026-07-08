import SwiftUI
import SwiftData
import PhotosUI

struct ImportView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var router: AppRouter

    @State private var title: String = ""
    @State private var selectedVideoItem: PhotosPickerItem?
    @State private var sourceVideoName: String = "未选择视频"
    @State private var importedVideo: ImportedVideo?
    @State private var isImporting = false
    @State private var importErrorMessage: String?

    private let importedVideoStore = ImportedVideoStore()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VideoImportCard(
                    sourceVideoName: sourceVideoName,
                    importedVideoDuration: importedVideo?.duration
                )

                VStack(alignment: .leading, spacing: 14) {
                    Text("视频来源")
                        .font(.headline)

                    PhotosPicker(selection: $selectedVideoItem, matching: .videos) {
                        Label("从相册选择视频", systemImage: "photo.on.rectangle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button {
                        let previousSourceVideoName = sourceVideoName
                        selectedVideoItem = nil
                        importedVideo = nil
                        importErrorMessage = nil
                        sourceVideoName = "未选择视频"
                        if title == previousSourceVideoName {
                            title = ""
                        }
                    } label: {
                        Label("清除当前选择", systemImage: "xmark.circle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)

                    if isImporting {
                        ProgressView("正在导入视频...")
                    }

                    if let importErrorMessage {
                        Text(importErrorMessage)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 14) {
                    Text("学习项目")
                        .font(.headline)

                    TextField("例如：XG - GALA", text: $title)
                        .textInputAutocapitalization(.never)
                        .textFieldStyle(.roundedBorder)

                    if let importedVideo {
                        Text("时长 \(formattedDuration(importedVideo.duration))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Button {
                        guard let importedVideo else { return }

                        let project = DanceProject(
                            title: normalizedTitle,
                            sourceVideoName: importedVideo.displayName,
                            sourceVideoPath: importedVideo.fileURL.path,
                            videoDuration: importedVideo.duration,
                            phase: .analyzing
                        )
                        modelContext.insert(project)
                        router.push(.analysis(projectId: project.id))
                    } label: {
                        Label("创建并开始分析", systemImage: "waveform.path.ecg")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(normalizedTitle.isEmpty || importedVideo == nil || isImporting)
                }
                .padding(16)
                .cardBackground()
            }
            .padding(18)
        }
        .background(AppUI.background)
        .task(id: selectedVideoItem) {
            guard let selectedVideoItem else { return }
            await importSelectedVideo(selectedVideoItem)
        }
        .onChange(of: selectedVideoItem) { _, newValue in
            if newValue == nil && !isImporting && importedVideo == nil {
                sourceVideoName = "未选择视频"
            }
        }
        .navigationTitle("导入视频")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var normalizedTitle: String {
        title.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    @MainActor
    private func importSelectedVideo(_ item: PhotosPickerItem) async {
        isImporting = true
        importErrorMessage = nil
        importedVideo = nil

        do {
            guard let sourceURL = try await item.loadTransferable(type: URL.self) else {
                throw ImportError.unreadableSelection
            }

            let imported = try await importedVideoStore.copyVideo(from: sourceURL)
            importedVideo = imported
            sourceVideoName = imported.displayName

            if normalizedTitle.isEmpty {
                title = imported.displayName
            }
        } catch {
            importedVideo = nil
            sourceVideoName = "未选择视频"
            importErrorMessage = "视频导入失败，请重新选择。"
        }

        isImporting = false
    }

    private func formattedDuration(_ duration: Double) -> String {
        formatDuration(duration)
    }
}

private enum ImportError: Error {
    case unreadableSelection
}

private struct VideoImportCard: View {
    let sourceVideoName: String
    let importedVideoDuration: Double?

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 8)
                .fill(
                    LinearGradient(
                        colors: [.black, AppUI.coral.opacity(0.75), AppUI.violet.opacity(0.85)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: "play.rectangle.fill")
                    .font(.system(size: 42))
                    .foregroundStyle(.white)

                Text("导入舞蹈视频")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.white)

                Text(sourceVideoName)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.8))
                    .lineLimit(1)

                if let importedVideoDuration {
                    Text("时长 \(formattedDuration(importedVideoDuration))")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.9))
                }
            }
            .padding(20)
        }
        .frame(height: 210)
    }

    private func formattedDuration(_ duration: Double) -> String {
        formatDuration(duration)
    }
}

private func formatDuration(_ duration: Double) -> String {
    let totalSeconds = max(Int(duration.rounded()), 0)
    let minutes = totalSeconds / 60
    let seconds = totalSeconds % 60
    return String(format: "%d:%02d", minutes, seconds)
}
