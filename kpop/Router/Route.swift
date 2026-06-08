import Foundation

enum Route: Hashable {
    case importVideo
    case analysis(projectId: UUID)
    case dancerPick(projectId: UUID)
    case practice(projectId: UUID)
}

