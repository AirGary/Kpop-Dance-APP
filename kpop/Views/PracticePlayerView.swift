import AVKit
import SwiftUI

struct PracticePlayerView: View {
    let player: AVPlayer
    let isMirrored: Bool

    var body: some View {
        VideoPlayer(player: player)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .scaleEffect(x: isMirrored ? -1 : 1, y: 1)
    }
}
