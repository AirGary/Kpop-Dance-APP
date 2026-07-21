import CryptoKit
import Foundation

nonisolated enum AnalysisPackageError: Error, Equatable, Sendable {
    case invalidArchive
    case unsupportedCompression
    case unsafeMember(String)
    case duplicateMember(String)
    case missingMember(String)
    case memberHashMismatch(String)
    case decoding(String)
}

nonisolated struct AnalysisPackageManifest: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let candidateID: String
    let modelVersion: String
    let memberHashes: [String: String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case candidateID = "candidateId"
        case modelVersion
        case memberHashes
    }
}

nonisolated struct AnalysisConfidenceInterval: Codable, Equatable, Sendable {
    let startSeconds: Double
    let endSeconds: Double
    let confidence: Double
}

nonisolated struct AnalysisPoseKeypoint: Codable, Equatable, Sendable {
    let name: String
    let x: Double
    let y: Double
    let confidence: Double
}

nonisolated struct AnalysisPoseFrame: Codable, Equatable, Sendable {
    let timeSeconds: Double
    let confidence: Double
    let keypoints: [AnalysisPoseKeypoint]
}

nonisolated struct AnalysisSpotlightKeyframe: Codable, Equatable, Sendable {
    let timeSeconds: Double
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let confidence: Double
}

nonisolated enum AnalysisDifficulty: String, Codable, Equatable, Sendable {
    case easy
    case medium
    case hard
}

nonisolated struct AnalysisDifficultyReason: Codable, Equatable, Sendable {
    let code: String
    let label: String
}

nonisolated struct AnalysisPracticeSegment: Codable, Equatable, Sendable, Identifiable {
    let startSeconds: Double
    let endSeconds: Double
    let difficulty: AnalysisDifficulty
    let repeatGroupID: String?
    let reasons: [AnalysisDifficultyReason]

    var id: String {
        "\(startSeconds)-\(endSeconds)"
    }

    enum CodingKeys: String, CodingKey {
        case startSeconds
        case endSeconds
        case difficulty
        case repeatGroupID = "repeatGroupId"
        case reasons
    }
}

nonisolated struct AnalysisPackage: Equatable, Sendable {
    static let requiredMembers = [
        "confidence.json",
        "manifest.json",
        "pose-track.json",
        "spotlight-track.json",
        "timeline.json"
    ]

    let manifest: AnalysisPackageManifest
    let confidence: [AnalysisConfidenceInterval]
    let poseTrack: [AnalysisPoseFrame]
    let spotlightTrack: [AnalysisSpotlightKeyframe]
    let timeline: [AnalysisPracticeSegment]

    static func decode(_ data: Data) throws -> AnalysisPackage {
        let entries = try StoredZipArchive(data: data).entries
        let names = Set(entries.keys)
        guard names == Set(requiredMembers) else {
            if let missing = requiredMembers.first(where: { entries[$0] == nil }) {
                throw AnalysisPackageError.missingMember(missing)
            }
            throw AnalysisPackageError.unsafeMember(names.subtracting(requiredMembers).sorted().first ?? "")
        }

        let manifest = try decode(AnalysisPackageManifest.self, member: "manifest.json", from: entries)
        guard manifest.schemaVersion == 1 else { throw AnalysisPackageError.decoding("manifest.json") }
        let confidence = try decode([AnalysisConfidenceInterval].self, member: "confidence.json", from: entries)
        let poseTrack = try decode([AnalysisPoseFrame].self, member: "pose-track.json", from: entries)
        let spotlightTrack = try decode([AnalysisSpotlightKeyframe].self, member: "spotlight-track.json", from: entries)
        let timeline = try decode([AnalysisPracticeSegment].self, member: "timeline.json", from: entries)

        for member in requiredMembers where member != "manifest.json" {
            guard manifest.memberHashes[member] == digest(entries[member]!) else {
                throw AnalysisPackageError.memberHashMismatch(member)
            }
        }

        return AnalysisPackage(
            manifest: manifest,
            confidence: confidence,
            poseTrack: poseTrack,
            spotlightTrack: spotlightTrack,
            timeline: timeline
        )
    }

    private static func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func decode<T: Decodable>(
        _ type: T.Type,
        member: String,
        from entries: [String: Data]
    ) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: entries[member]!)
        } catch {
            throw AnalysisPackageError.decoding("\(member): \(error)")
        }
    }
}

nonisolated private struct StoredZipArchive {
    let entries: [String: Data]

    init(data: Data) throws {
        var offset = 0
        var values: [String: Data] = [:]

        while offset + 30 <= data.count {
            guard data.readUInt32LE(at: offset) == 0x04034b50 else { break }
            guard data.readUInt16LE(at: offset + 6) == 0 else {
                throw AnalysisPackageError.invalidArchive
            }
            guard data.readUInt16LE(at: offset + 8) == 0 else {
                throw AnalysisPackageError.unsupportedCompression
            }

            let flags = data.readUInt16LE(at: offset + 6)
            guard flags & 0x0008 == 0 else { throw AnalysisPackageError.invalidArchive }
            let crc = data.readUInt32LE(at: offset + 14)
            let size = Int(data.readUInt32LE(at: offset + 22))
            let nameLength = Int(data.readUInt16LE(at: offset + 26))
            let extraLength = Int(data.readUInt16LE(at: offset + 28))
            let nameStart = offset + 30
            let contentStart = nameStart + nameLength + extraLength
            guard
                nameLength > 0,
                contentStart >= nameStart,
                size >= 0,
                contentStart + size <= data.count,
                let name = String(data: data[nameStart..<(nameStart + nameLength)], encoding: .utf8)
            else { throw AnalysisPackageError.invalidArchive }

            guard AnalysisPackage.requiredMembers.contains(name), !name.contains(".."), !name.hasPrefix("/") else {
                throw AnalysisPackageError.unsafeMember(name)
            }
            guard values[name] == nil else { throw AnalysisPackageError.duplicateMember(name) }
            let content = Data(data[contentStart..<(contentStart + size)])
            guard CRC32.checksum(content) == crc else { throw AnalysisPackageError.invalidArchive }
            values[name] = content
            offset = contentStart + size
        }

        guard offset > 0 else { throw AnalysisPackageError.invalidArchive }
        entries = values
    }
}

private extension Data {
    nonisolated func readUInt16LE(at offset: Int) -> UInt16 {
        UInt16(self[offset]) | UInt16(self[offset + 1]) << 8
    }

    nonisolated func readUInt32LE(at offset: Int) -> UInt32 {
        UInt32(self[offset]) |
            UInt32(self[offset + 1]) << 8 |
            UInt32(self[offset + 2]) << 16 |
            UInt32(self[offset + 3]) << 24
    }
}

private enum CRC32 {
    nonisolated static func checksum(_ data: Data) -> UInt32 {
        var value: UInt32 = 0xffffffff
        for byte in data {
            value ^= UInt32(byte)
            for _ in 0..<8 {
                value = (value >> 1) ^ ((value & 1) == 1 ? 0xedb88320 : 0)
            }
        }
        return value ^ 0xffffffff
    }
}
