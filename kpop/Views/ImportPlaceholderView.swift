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
            VStack(alignment: .leading, spacing: 22) {
                VideoImportCard(
                    sourceVideoName: sourceVideoName,
                    importedVideoName: importedVideo?.displayName,
                    importedVideoDuration: importedVideo?.duration,
                    isImporting: isImporting,
                    hasImportedVideo: importedVideo != nil
                )

                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Step 1",
                        title: "导入视频素材",
                        detail: "选择本地相册中的固定机位练习视频。系统会复制一份本地副本，方便后续分析和播放器练习。"
                    )

                    PhotosPicker(selection: $selectedVideoItem, matching: .videos) {
                        Label("从相册选择视频", systemImage: "photo.on.rectangle.angled")
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
                    .disabled(selectedVideoItem == nil && importedVideo == nil && !isImporting)

                    ImportStatusBlock(
                        importedVideo: importedVideo,
                        isImporting: isImporting,
                        importErrorMessage: importErrorMessage
                    )
                }
                .padding(AppUI.panelPadding)
                .cardBackground(.primary)

                VStack(alignment: .leading, spacing: 16) {
                    StageSectionHeader(
                        eyebrow: "Step 2",
                        title: "建立学习项目",
                        detail: "给这条舞蹈流程一个名字。创建后会进入分析页，继续选择舞者并进入练习模式。"
                    )

                    VStack(alignment: .leading, spacing: 8) {
                        Text("项目标题")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(AppUI.ink)

                        TextField("例如：XG - GALA", text: $title)
                            .textInputAutocapitalization(.never)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: title) { _, newValue in
                                if newValue.trimmingCharacters(in: .whitespacesAndNewlines) != (importedVideo?.displayName ?? "") {
                                    isTitleAutofilledFromImport = false
                                }
                            }
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        StageInfoRow(
                            title: "当前素材",
                            value: importedVideo?.displayName ?? "等待导入视频",
                            systemImage: "film"
                        )
                        StageInfoRow(
                            title: "时长摘要",
                            value: importedVideo.map { formattedDuration($0.duration) } ?? "导入后自动生成",
                            systemImage: "clock"
                        )
                    }
                    .padding(14)
                    .cardBackground(.muted)

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
                .padding(AppUI.panelPadding)
                .cardBackground(.primary)
            }
            .padding(20)
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
            guard let pickedVideo = try await item.loadTransferable(type: PickedVideo.self) else {
                throw ImportError.unreadableSelection
            }
            defer { try? FileManager.default.removeItem(at: pickedVideo.fileURL) }

            let imported = try await importedVideoStore.copyVideo(
                from: pickedVideo.fileURL,
                displayName: pickedVideo.displayName
            )
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
    let hasImportedVideo: Bool

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 32, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            .black,
                            AppUI.coral.opacity(0.82),
                            AppUI.violet.opacity(0.92)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            Circle()
                .fill(.white.opacity(0.12))
                .frame(width: 190, height: 190)
                .offset(x: 90, y: -50)

            VStack(alignment: .leading, spacing: 12) {
                StatusBadge(
                    text: hasImportedVideo ? "素材已就绪" : (isImporting ? "导入中" : "等待素材"),
                    systemImage: hasImportedVideo ? "checkmark.circle.fill" : "arrow.down.circle.fill",
                    color: .white
                )

                Text("建立新的练习素材")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.white)

                Text(sourceVideoName)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.85))
                    .lineLimit(2)

                HStack(spacing: 12) {
                    HeroFact(title: "文件名", value: importedVideoName ?? "未导入")
                    HeroFact(title: "时长", value: importedVideoDuration.map(formatDuration(_:)) ?? "--:--")
                }

                if isImporting {
                    Text("系统正在复制视频并准备本地练习副本。")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.82))
                }
            }
            .padding(24)
        }
        .frame(height: 250)
    }
}

private struct ImportStatusBlock: View {
    let importedVideo: ImportedVideo?
    let isImporting: Bool
    let importErrorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if isImporting {
                HStack(spacing: 10) {
                    ProgressView()
                    VStack(alignment: .leading, spacing: 2) {
                        Text("正在导入视频...")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(AppUI.ink)
                        Text("正在复制视频到本地并生成练习素材，请稍候。")
                            .font(.caption)
                            .foregroundStyle(AppUI.inkSoft)
                    }
                }
            } else if let importedVideo {
                VStack(alignment: .leading, spacing: 10) {
                    StageInfoRow(title: "文件名", value: importedVideo.displayName, systemImage: "film.stack")
                    StageInfoRow(title: "素材时长", value: formatDuration(importedVideo.duration), systemImage: "clock.fill")
                }
            } else if let importErrorMessage {
                Label(importErrorMessage, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppUI.coral)
            } else {
                Text("选择视频后，这里会显示素材摘要、时长和导入状态。")
                    .font(.subheadline)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .cardBackground(.muted)
    }
}

private func formatDuration(_ duration: Double) -> String {
    let totalSeconds = max(Int(duration.rounded()), 0)
    let minutes = totalSeconds / 60
    let seconds = totalSeconds % 60
    return String(format: "%d:%02d", minutes, seconds)
}

#Preview("Import Idle") {
    NavigationStack {
        ImportView()
            .environmentObject(AppRouter())
    }
    .modelContainer(PreviewProjects.previewContainer(projects: []))
}
