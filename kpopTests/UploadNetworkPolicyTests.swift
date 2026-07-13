import Foundation
import Testing
@testable import kpop

struct UploadNetworkPolicyTests {
    @Test
    func defaultConfigurationRejectsExpensiveNetworks() {
        let configuration = UploadNetworkPolicy.configuration(allowsCellular: false)

        #expect(configuration.allowsCellularAccess == true)
        #expect(configuration.allowsExpensiveNetworkAccess == false)
    }

    @Test
    func oneTimeCellularConfigurationAllowsExpensiveNetworks() {
        let configuration = UploadNetworkPolicy.configuration(allowsCellular: true)

        #expect(configuration.allowsCellularAccess == true)
        #expect(configuration.allowsExpensiveNetworkAccess == true)
    }
}
