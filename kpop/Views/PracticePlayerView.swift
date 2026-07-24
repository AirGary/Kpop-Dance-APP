import AVFoundation
import SwiftUI

struct PracticePlayerView: View {
    let player: AVPlayer
    let isMirrored: Bool

    var body: some View {
        PortraitFollowPlayerView(player: player, isMirrored: isMirrored)
    }
}
