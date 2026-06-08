import SwiftUI
import SwiftData
import PhotosUI

struct ImportView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var router: AppRouter

    @State private var title: String = ""
    @State private var selectedVideoItem: PhotosPickerItem?
    @State private var sourceVideoName: String = "未选择视频"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VideoImportCard(sourceVideoName: sourceVideoName)

                VStack(alignment: .leading, spacing: 14) {
                    Text("视频来源")
                        .font(.headline)

                    PhotosPicker(selection: $selectedVideoItem, matching: .videos) {
                        Label("从相册选择视频", systemImage: "photo.on.rectangle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button {
                        title = "XG - GALA"
                        sourceVideoName = "Demo: XG - GALA 固定机位"
                        selectedVideoItem = nil
                    } label: {
                        Label("使用示例视频信息", systemImage: "sparkles")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                .padding(16)
                .cardBackground()

                VStack(alignment: .leading, spacing: 14) {
                    Text("学习项目")
                        .font(.headline)

                    TextField("例如：XG - GALA", text: $title)
                        .textInputAutocapitalization(.never)
                        .textFieldStyle(.roundedBorder)

                    Button {
                        let project = DanceProject(
                            title: normalizedTitle,
                            sourceVideoName: sourceVideoName,
                            phase: .analyzing
                        )
                        modelContext.insert(project)
                        router.push(.analysis(projectId: project.id))
                    } label: {
                        Label("创建并开始分析", systemImage: "waveform.path.ecg")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(normalizedTitle.isEmpty)
                }
                .padding(16)
                .cardBackground()
            }
            .padding(18)
        }
        .background(AppUI.background)
        .onChange(of: selectedVideoItem) { _, newValue in
            if newValue != nil {
                sourceVideoName = "相册视频"
                if normalizedTitle.isEmpty {
                    title = "新的舞蹈项目"
                }
            }
        }
        .navigationTitle("导入视频")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var normalizedTitle: String {
        title.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private struct VideoImportCard: View {
    let sourceVideoName: String

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
            }
            .padding(20)
        }
        .frame(height: 210)
    }
}
