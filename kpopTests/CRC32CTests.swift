import Foundation
import Testing
@testable import kpop

struct CRC32CTests {
    @Test
    func streamsFileAndEncodesChecksumInNetworkByteOrder() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("CRC32C-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: url) }
        try Data("123456789".utf8).write(to: url)

        let checksum = try CRC32C.base64EncodedChecksum(fileURL: url)

        #expect(checksum == "4waSgw==")
    }
}
