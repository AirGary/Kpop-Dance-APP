import SwiftUI
import SwiftData

enum AppUI {
    static let background = Color(red: 0.95, green: 0.97, blue: 0.99)
    static let panel = Color.white
    static let panelMuted = Color(red: 0.92, green: 0.95, blue: 0.98)
    static let panelTinted = Color(red: 0.89, green: 0.93, blue: 0.99)
    static let ink = Color(red: 0.08, green: 0.09, blue: 0.12)
    static let inkSoft = Color(red: 0.29, green: 0.33, blue: 0.42)
    static let divider = Color.black.opacity(0.08)
    static let shadow = Color(red: 0.09, green: 0.11, blue: 0.17).opacity(0.08)
    static let violet = Color(red: 0.45, green: 0.32, blue: 0.86)
    static let cyan = Color(red: 0.05, green: 0.65, blue: 0.78)
    static let coral = Color(red: 0.96, green: 0.38, blue: 0.34)
    static let lime = Color(red: 0.34, green: 0.72, blue: 0.40)
    static let amber = Color(red: 0.95, green: 0.69, blue: 0.22)
    static let cardRadius: CGFloat = 24
    static let panelPadding: CGFloat = 18
}

enum AppCardTone {
    case primary
    case muted
    case tinted

    var fill: Color {
        switch self {
        case .primary: AppUI.panel
        case .muted: AppUI.panelMuted
        case .tinted: AppUI.panelTinted
        }
    }
}

struct CardBackground: ViewModifier {
    let tone: AppCardTone

    func body(content: Content) -> some View {
        content
            .background(
                tone.fill,
                in: RoundedRectangle(cornerRadius: AppUI.cardRadius, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppUI.cardRadius, style: .continuous)
                    .stroke(AppUI.divider, lineWidth: 1)
            )
            .shadow(color: AppUI.shadow, radius: 14, x: 0, y: 8)
    }
}

extension View {
    func cardBackground(_ tone: AppCardTone = .primary) -> some View {
        modifier(CardBackground(tone: tone))
    }
}

struct StageSectionHeader: View {
    let eyebrow: String?
    let title: String
    let detail: String?

    init(eyebrow: String? = nil, title: String, detail: String? = nil) {
        self.eyebrow = eyebrow
        self.title = title
        self.detail = detail
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let eyebrow {
                Text(eyebrow.uppercased())
                    .font(.caption.weight(.bold))
                    .tracking(1.2)
                    .foregroundStyle(AppUI.violet)
            }

            Text(title)
                .font(.title3.weight(.bold))
                .foregroundStyle(AppUI.ink)

            if let detail {
                Text(detail)
                    .font(.subheadline)
                    .foregroundStyle(AppUI.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

struct StatusBadge: View {
    let text: String
    let systemImage: String
    let color: Color

    var body: some View {
        Label(text, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(color.opacity(0.12), in: Capsule())
    }
}

struct MetricTile: View {
    let value: String
    let label: String
    let detail: String
    let icon: String
    let accent: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: icon)
                .font(.headline.weight(.bold))
                .foregroundStyle(accent)
                .frame(width: 34, height: 34)
                .background(accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            Text(value)
                .font(.title3.weight(.bold))
                .foregroundStyle(AppUI.ink)

            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppUI.ink)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .cardBackground(.primary)
    }
}

struct HeroFact: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.74))
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

struct StageInfoRow: View {
    let title: String
    let value: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(AppUI.violet)
                .frame(width: 30, height: 30)
                .background(AppUI.violet.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(AppUI.inkSoft)
                Text(value)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppUI.ink)
            }
        }
    }
}

enum PreviewProjects {
    @MainActor
    static func sampleProjects() -> [DanceProject] {
        [
            DanceProject(
                title: "XG - GALA",
                sourceVideoName: "XG GALA Dance Practice",
                videoDuration: 76,
                selectedDancerName: "Dancer 2",
                defaultPlaybackRate: PlaybackRate.threeQuarter.rawValue,
                phase: .practicing
            ),
            DanceProject(
                title: "LE SSERAFIM - CRAZY",
                sourceVideoName: "Practice Cam",
                videoDuration: 92,
                selectedDancerName: "Dancer 1",
                phase: .readyToPractice
            ),
            DanceProject(
                title: "ILLIT - Magnetic",
                sourceVideoName: "Studio Take",
                videoDuration: 64,
                phase: .analyzing
            )
        ]
    }

    @MainActor
    static func previewContainer() -> ModelContainer {
        previewContainer(projects: sampleProjects())
    }

    @MainActor
    static func previewContainer(projects: [DanceProject]) -> ModelContainer {
        do {
            let config = ModelConfiguration(isStoredInMemoryOnly: true)
            let container = try ModelContainer(for: DanceProject.self, configurations: config)
            let context = container.mainContext

            for project in projects {
                context.insert(project)
            }

            return container
        } catch {
            fatalError("Failed to create preview container: \(error)")
        }
    }
}
