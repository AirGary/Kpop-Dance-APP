import SwiftUI

struct AnalysisView: View {
    @EnvironmentObject private var router: AppRouter
    @Environment(\.jobsAPIClient) private var jobsAPIClient
    @Environment(\.analysisService) private var analysisService
    @Environment(\.uploadRunner) private var uploadRunner
    @State private var connectionModel = AnalysisConnectionModel()
    @State private var uploadModel = UploadConnectionModel()
    @State private var showsCellularConfirmation = false
    @State private var realAnalysisModel: RealAnalysisModel?
    let project: DanceProject

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 14) {
                    StageSectionHeader(
                        eyebrow: "Analysis",
                        title: project.title,
                        detail: "整理关键帧、节拍和动作节点，为后续舞者选择与练习时间轴做准备。"
                    )

                    HStack {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(project.sourceVideoName)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(AppUI.inkSoft)
                        }

                        Spacer()

                        StatusBadge(text: project.phase.title, systemImage: project.phase.systemImage, color: statusColor)
                    }

                    ProgressView(value: progress)
                        .tint(statusColor)

                    Text("分析进度 \(Int(progress * 100))%")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppUI.inkSoft)
                }
                .padding(AppUI.panelPadding)
                .cardBackground()

                uploadCard

                localBackendCard

                if let realAnalysisModel {
                    realAnalysisCard(realAnalysisModel)
                }

                VStack(alignment: .leading, spacing: 12) {
                    StageSectionHeader(
                        eyebrow: "Pipeline",
                        title: "分析步骤",
                        detail: "当前以轻量流程模拟真实分析阶段，界面会保持和后续播放器一致的训练工具风格。"
                    )

                    ForEach(Array(DanceProject.analysisSteps.enumerated()), id: \.element.id) { index, step in
                        AnalysisStepRow(
                            step: step,
                            isActive: index <= activeStepIndex,
                            isLast: index == DanceProject.analysisSteps.count - 1
                        )
                    }
                }
                .padding(AppUI.panelPadding)
                .cardBackground()

                if realAnalysisModel == nil {
                    VStack(spacing: 10) {
                    Button(project.phase == .failed ? "重试分析" : "开始/继续分析") {
                        setPhase(.analyzing)
                    }
                    .buttonStyle(.bordered)
                    .frame(maxWidth: .infinity)

                    Button {
                        setPhase(.needsDancerSelection)
                        router.replaceTop(with: .dancerPick(projectId: project.id))
                    } label: {
                        Label("完成分析，选择舞者", systemImage: "figure.dance")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button(role: .destructive) {
                        setPhase(.failed)
                    } label: {
                        Label("标记分析失败", systemImage: "exclamationmark.triangle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    }
                    .padding(AppUI.panelPadding)
                    .cardBackground()
                }
            }
            .padding(20)
        }
        .background(AppUI.background)
        .navigationTitle("分析")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog(
            "本次允许使用蜂窝网络？",
            isPresented: $showsCellularConfirmation,
            titleVisibility: .visible
        ) {
            Button("允许并继续上传") {
                startUpload(allowsCellular: true)
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("视频上传可能消耗较多流量。本次确认不会保存为全局设置。")
        }
        .task(id: project.remoteJobId) {
            guard
                let analysisService,
                project.remoteJobId != nil,
                realAnalysisModel == nil
            else { return }
            let model = RealAnalysisModel(service: analysisService)
            realAnalysisModel = model
            await model.start(project: project)
        }
    }

    private var uploadCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            StageSectionHeader(
                eyebrow: "Video Upload",
                title: "准备云端分析素材",
                detail: "生成最高 1080p 的 H.264 MP4 副本并断点续传。原始视频不会被修改。"
            )

            uploadStatus

            if !isUploadBusy {
                Button {
                    startUpload(allowsCellular: false)
                } label: {
                    Label(primaryUploadTitle, systemImage: "arrow.up.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(uploadRunner == nil || project.sourceVideoPath == nil)

                Button {
                    showsCellularConfirmation = true
                } label: {
                    Label("本次允许使用蜂窝网络", systemImage: "antenna.radiowaves.left.and.right")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(uploadRunner == nil || project.sourceVideoPath == nil)
            }

            if uploadRunner == nil {
                Text("视频上传仅在 Debug 模拟器版本启用。")
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .padding(AppUI.panelPadding)
        .cardBackground()
    }

    @ViewBuilder
    private var uploadStatus: some View {
        switch uploadModel.state {
        case .ready:
            Label("视频将在本机压缩后上传", systemImage: "film.stack")
                .foregroundStyle(AppUI.inkSoft)
        case .compressing:
            uploadActivity(title: "正在生成 1080p 压缩副本", detail: "只处理受管副本，原视频保持不变。")
        case .hashing:
            uploadActivity(title: "正在校验压缩副本", detail: "计算 SHA-256，确保服务端收到完整文件。")
        case .uploading(let progress):
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("正在断点续传")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(Int(progress * 100))%")
                        .font(.caption.monospacedDigit().weight(.bold))
                        .foregroundStyle(AppUI.violet)
                }
                ProgressView(value: progress)
                    .tint(AppUI.violet)
            }
        case .validating:
            uploadActivity(title: "服务端正在验证视频", detail: "核对文件大小与 SHA-256，随后创建分析任务。")
        case .completed(let jobID):
            VStack(alignment: .leading, spacing: 8) {
                StatusBadge(text: "上传完成", systemImage: "checkmark.icloud.fill", color: .green)
                Text("分析任务 \(String(jobID.uuidString.prefix(8))) 已创建，只上传了压缩副本。")
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        case .failed(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline)
                .foregroundStyle(.red)
        }
    }

    private func uploadActivity(title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ProgressView()
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
    }

    private var isUploadBusy: Bool {
        switch uploadModel.state {
        case .compressing, .hashing, .uploading, .validating:
            true
        case .ready, .completed, .failed:
            false
        }
    }

    private var primaryUploadTitle: String {
        if case .failed = uploadModel.state {
            return "继续上传"
        }
        return "压缩并上传视频"
    }

    private func startUpload(allowsCellular: Bool) {
        guard let uploadRunner else { return }
        Task {
            await uploadModel.start(
                project: project,
                runner: uploadRunner,
                allowsCellular: allowsCellular
            )
        }
    }

    private var localBackendCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            StageSectionHeader(
                eyebrow: "Local API",
                title: "元数据诊断连接",
                detail: "开发者诊断入口只发送视频元数据，用于单独检查 Jobs API。"
            )

            switch connectionModel.state {
            case .idle:
                connectionButton(title: "创建云分析任务")
            case .loading:
                HStack(spacing: 10) {
                    ProgressView()
                    Text("正在连接本地后端…")
                        .font(.subheadline.weight(.semibold))
                }
            case .connected(let job):
                HStack {
                    StatusBadge(text: job.state.rawValue, systemImage: "checkmark.icloud", color: .green)
                    Spacer()
                    Text(String(job.id.uuidString.prefix(8)))
                        .font(.caption.monospaced().weight(.semibold))
                        .foregroundStyle(AppUI.inkSoft)
                }
                ProgressView(value: job.progress)
                    .tint(.green)
            case .failed(let message):
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.red)
                connectionButton(title: "重新连接")
            }

            if jobsAPIClient == nil {
                Text("本地 API 仅在 Debug 模拟器版本启用。")
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .padding(AppUI.panelPadding)
        .cardBackground()
    }

    private func realAnalysisCard(_ model: RealAnalysisModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            StageSectionHeader(
                eyebrow: "REAL ANALYSIS",
                title: "本地 AI 分析状态",
                detail: "候选舞者和分析进度来自本地 FastAPI 与真实 Worker。"
            )
            switch model.state {
            case .idle, .loading:
                HStack { ProgressView(); Text("正在读取真实分析任务…") }
            case .detecting(let snapshot):
                analysisProgress(snapshot, title: "正在检测真实舞者")
            case .awaitingTarget(let candidates):
                Label(
                    candidates.isEmpty ? "尚未得到有效候选舞者" : "已找到 \(candidates.count) 名候选舞者",
                    systemImage: candidates.isEmpty ? "person.crop.circle.badge.questionmark" : "person.3.fill"
                )
                if !candidates.isEmpty {
                    Button {
                        router.replaceTop(with: .dancerPick(projectId: project.id))
                    } label: {
                        Label("选择目标舞者", systemImage: "figure.dance")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                }
            case .selecting(let candidateID):
                HStack { ProgressView(); Text("正在提交目标舞者 \(candidateID)…") }
            case .analyzing(let snapshot):
                analysisProgress(snapshot, title: "正在生成目标分析")
            case .resultReady:
                StatusBadge(text: "分析结果已就绪", systemImage: "checkmark.circle.fill", color: .green)
            case .failed(let message, let recoverable):
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                if recoverable {
                    Button("重试读取状态") {
                        Task { await model.start(project: project) }
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding(AppUI.panelPadding)
        .cardBackground()
    }

    private func analysisProgress(_ snapshot: AnalysisJobSnapshot, title: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                ProgressView()
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                Text("\(Int(snapshot.progress * 100))%")
                    .font(.caption.monospacedDigit().weight(.bold))
            }
            ProgressView(value: snapshot.progress)
                .tint(AppUI.violet)
        }
    }

    private func connectionButton(title: String) -> some View {
        Button {
            guard let jobsAPIClient else { return }
            Task {
                await connectionModel.connect(project: project, client: jobsAPIClient)
            }
        } label: {
            Label(title, systemImage: "cloud.fill")
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .disabled(jobsAPIClient == nil)
    }

    private var progress: Double {
        switch project.phase {
        case .created: 0.1
        case .analyzing: 0.55
        case .needsDancerSelection: 1.0
        case .readyToPractice, .practicing: 1.0
        case .failed: 0.35
        }
    }

    private var activeStepIndex: Int {
        switch project.phase {
        case .created: 0
        case .analyzing: 2
        case .needsDancerSelection, .readyToPractice, .practicing: 3
        case .failed: 1
        }
    }

    private var statusColor: Color {
        switch project.phase {
        case .created: .gray
        case .analyzing: AppUI.violet
        case .needsDancerSelection: .orange
        case .readyToPractice, .practicing: .green
        case .failed: .red
        }
    }

    private func setPhase(_ phase: ProjectPhase) {
        project.phase = phase
        project.updatedAt = Date()
    }
}

private struct AnalysisStepRow: View {
    let step: AnalysisStep
    let isActive: Bool
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 6) {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(isActive ? AppUI.cyan : .secondary)

                if !isLast {
                    Rectangle()
                        .fill(isActive ? AppUI.cyan.opacity(0.45) : Color.secondary.opacity(0.18))
                        .frame(width: 2, height: 30)
                }
            }

            Image(systemName: step.systemImage)
                .frame(width: 28, height: 28)
                .foregroundStyle(isActive ? AppUI.violet : .secondary)

            VStack(alignment: .leading, spacing: 3) {
                Text(step.title)
                    .font(.subheadline.weight(.semibold))
                Text(step.detail)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .padding(.vertical, 4)
    }
}
