import Foundation

nonisolated enum CRC32C {
    private static let table: [UInt32] = (0..<256).map { value in
        var checksum = UInt32(value)
        for _ in 0..<8 {
            checksum = checksum & 1 == 1
                ? (checksum >> 1) ^ 0x82F63B78
                : checksum >> 1
        }
        return checksum
    }

    static func base64EncodedChecksum(fileURL: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        var checksum = UInt32.max

        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
            for byte in data {
                let index = Int((checksum ^ UInt32(byte)) & 0xFF)
                checksum = table[index] ^ (checksum >> 8)
            }
        }

        var networkOrder = (checksum ^ UInt32.max).bigEndian
        return withUnsafeBytes(of: &networkOrder) { bytes in
            Data(bytes).base64EncodedString()
        }
    }
}
