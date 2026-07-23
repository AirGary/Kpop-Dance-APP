import CryptoKit
import Foundation
import Testing
@testable import kpop

struct AnalysisPackageTests {
    @Test
    func decodesAndValidatesStoredAnalysisPackage() throws {
        let entries = fixtureEntries()
        let data = try makeStoredZip(entries: entries)

        let package: AnalysisPackage
        do {
            package = try AnalysisPackage.decode(data)
        } catch {
            Issue.record("Analysis package decode failed: \(error)")
            return
        }

        #expect(package.manifest.schemaVersion == 1)
        #expect(package.manifest.candidateID == "candidate-1")
        #expect(package.poseTrack.count == 1)
        #expect(package.poseTrack.allSatisfy { frame in
            frame.keypoints.contains(where: { $0.name == "left_wrist" })
                && frame.keypoints.contains(where: { $0.name == "right_wrist" })
                && frame.keypoints.contains(where: { $0.name == "left_ankle" })
                && frame.keypoints.contains(where: { $0.name == "right_ankle" })
        })
        #expect(package.spotlightTrack[0].confidence == 0.9)
        #expect(package.timeline[0].difficulty == .hard)
        #expect(package.timeline[0].repeatGroupID == "repeat-1")
    }

    @Test
    func rejectsUnsafeOrIncompletePackageMembers() throws {
        var entries = fixtureEntries()
        entries["../manifest.json"] = entries.removeValue(forKey: "manifest.json")!
        let traversalData = try makeStoredZip(entries: entries)
        #expect(throws: AnalysisPackageError.self) {
            try AnalysisPackage.decode(traversalData)
        }

        var missing = fixtureEntries()
        missing.removeValue(forKey: "confidence.json")
        let missingData = try makeStoredZip(entries: missing)
        #expect(throws: AnalysisPackageError.self) {
            try AnalysisPackage.decode(missingData)
        }
    }

    @Test
    func packageStoreChecksServerMetadataBeforePublishing() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = AnalysisPackageStore(rootDirectory: root)
        let data = Data("package".utf8)

        #expect(throws: AnalysisPackageStoreError.metadataMismatch) {
            try store.save(
                data,
                projectID: UUID(),
                version: 1,
                expectedSHA256: String(repeating: "0", count: 64),
                expectedByteCount: data.count
            )
        }
    }

    private func fixtureEntries() -> [String: Data] {
        let confidence = Data(#"[{"startSeconds":0,"endSeconds":1,"confidence":0.9}]"#.utf8)
        let pose = Data(#"[{"timeSeconds":0,"confidence":0.9,"keypoints":[{"name":"left_wrist","x":0.35,"y":0.4,"confidence":0.9},{"name":"right_wrist","x":0.65,"y":0.4,"confidence":0.9},{"name":"left_ankle","x":0.4,"y":0.9,"confidence":0.9},{"name":"right_ankle","x":0.6,"y":0.9,"confidence":0.9}]}]"#.utf8)
        let spotlight = Data(#"[{"timeSeconds":0,"x":0.2,"y":0.1,"width":0.3,"height":0.7,"confidence":0.9}]"#.utf8)
        let timeline = Data(#"[{"startSeconds":0,"endSeconds":1,"difficulty":"hard","repeatGroupId":"repeat-1","reasons":[{"code":"speed","label":"快速动作"}]}]"#.utf8)
        let hashes = [
            "confidence.json": digest(confidence),
            "pose-track.json": digest(pose),
            "spotlight-track.json": digest(spotlight),
            "timeline.json": digest(timeline)
        ]
        let manifest = Data(#"{"schemaVersion":1,"candidateId":"candidate-1","modelVersion":"rtmdet-m+rtmpose-m","memberHashes":\#(json(hashes))}"#.utf8)
        return [
            "confidence.json": confidence,
            "manifest.json": manifest,
            "pose-track.json": pose,
            "spotlight-track.json": spotlight,
            "timeline.json": timeline
        ]
    }

    private func makeStoredZip(entries: [String: Data]) throws -> Data {
        var output = Data()
        for (name, content) in entries.sorted(by: { $0.key < $1.key }) {
            let nameData = Data(name.utf8)
            output.append(contentsOf: littleEndian(UInt32(0x04034b50)))
            output.append(contentsOf: littleEndian(UInt16(20)))
            output.append(contentsOf: littleEndian(UInt16(0)))
            output.append(contentsOf: littleEndian(UInt16(0)))
            output.append(contentsOf: littleEndian(UInt16(0)))
            output.append(contentsOf: littleEndian(UInt16(0)))
            output.append(contentsOf: littleEndian(UInt32(crc32(content))))
            output.append(contentsOf: littleEndian(UInt32(content.count)))
            output.append(contentsOf: littleEndian(UInt32(content.count)))
            output.append(contentsOf: littleEndian(UInt16(nameData.count)))
            output.append(contentsOf: littleEndian(UInt16(0)))
            output.append(nameData)
            output.append(content)
        }
        return output
    }

    private func json(_ value: [String: String]) -> String {
        let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }

    private func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func littleEndian<T: FixedWidthInteger>(_ value: T) -> Data {
        withUnsafeBytes(of: value.littleEndian) { Data($0) }
    }

    private func crc32(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xffffffff
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0..<8 {
                crc = (crc >> 1) ^ ((crc & 1) == 1 ? 0xedb88320 : 0)
            }
        }
        return crc ^ 0xffffffff
    }
}
