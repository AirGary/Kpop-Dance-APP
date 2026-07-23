import AVFoundation
import SwiftUI
import UIKit

struct PortraitFollowPlayerView: UIViewRepresentable {
    let player: AVPlayer
    let isMirrored: Bool

    func makeUIView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.player = player
        view.isMirrored = isMirrored
        return view
    }

    func updateUIView(_ view: PlayerLayerView, context: Context) {
        view.player = player
        view.isMirrored = isMirrored
    }
}

final class PlayerLayerView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }

    var player: AVPlayer? {
        didSet { playerLayer.player = player }
    }

    var isMirrored = false {
        didSet {
            playerLayer.setAffineTransform(isMirrored ? CGAffineTransform(scaleX: -1, y: 1) : .identity)
        }
    }

    private var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }

    override init(frame: CGRect) {
        super.init(frame: frame)
        playerLayer.videoGravity = .resizeAspect
        backgroundColor = .black
    }

    required init?(coder: NSCoder) { nil }
}
