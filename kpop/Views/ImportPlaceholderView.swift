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
    @State private var activeImportRequestID = UUID()
    @State private var isTitleAutofilledFromImport = false

    private let importedVideoStore = ImportedVideoStore()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VideoImportCard(
                    sourceVideoName: sourceVideoName,
                    importedVideoName: importedVideo?.displayName,
                    importedVideoDuration: importedVideo?.duration,
                    isImporting: isImporting
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
                        invalidateImportRequest()
                        selectedVideoItem = nil
                        importedVideo = nil
                        isImporting = false
                        importErrorMessage = nil
                        sourceVideoName = "未选择视频"
                        if isTitleAutofilledFromImport {
                            title = ""
                            isTitleAutofilledFromImport = false
                        }
                    } label: {
                        Label("清除当前选择", systemImage: "xmark.circle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)

                    if isImporting {
                        ProgressView("正在导入视频...")
                        Text("正在复制视频到本地并生成练习素材，请稍候。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                        .onChange(of: title) { _, newValue in
                            if newValue.trimmingCharacters(in: .whitespacesAndNewlines) != (importedVideo?.displayName ?? "") {
                                isTitleAutofilledFromImport = false
                            }
                        }

                    if let importedVideo {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("文件名：\(importedVideo.displayName)")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Text("时长：\(formattedDuration(importedVideo.duration))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("导入后会自动显示文件名和时长摘要。")
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
            let requestID = UUID()
            activeImportRequestID = requestID
            await importSelectedVideo(selectedVideoItem, requestID: requestID)
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
    private func importSelectedVideo(_ item: PhotosPickerItem, requestID: UUID) async {
        isImporting = true
        importErrorMessage = nil
        importedVideo = nil

        do {
            guard let sourceURL = try await item.loadTransferable(type: URL.self) else {
                throw ImportError.unreadableSelection
            }

            let imported = try await importedVideoStore.copyVideo(from: sourceURL)
            guard isActiveImportRequest(requestID) else { return }
            importedVideo = imported
            sourceVideoName = imported.displayName

            if normalizedTitle.isEmpty {
                title = imported.displayName
                isTitleAutofilledFromImport = true
            }
            isImporting = false
        } catch {
            guard isActiveImportRequest(requestID) else { return }
            importedVideo = nil
            sourceVideoName = "未选择视频"
            importErrorMessage = "视频导入失败，请重新选择。"
            isImporting = false
        }
    }

    private func formattedDuration(_ duration: Double) -> String {
        formatDuration(duration)
    }

    private func isActiveImportRequest(_ requestID: UUID) -> Bool {
        activeImportRequestID == requestID
    }

    private func invalidateImportRequest() {
        activeImportRequestID = UUID()
    }
}

private enum ImportError: Error {
    case unreadableSelection
}

private struct VideoImportCard: View {
    let sourceVideoName: String
    let importedVideoName: String?
    let importedVideoDuration: Double?
    let isImporting: Bool

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

                if let importedVideoName {
                    Text("文件名：\(importedVideoName)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.9))
                }

                if let importedVideoDuration {
                    Text("时长：\(formattedDuration(importedVideoDuration))")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.9))
                }

                if isImporting {
                    Text("导入中，完成后会自动创建本地副本。")
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
