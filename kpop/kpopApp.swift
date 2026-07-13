//
//  kpopApp.swift
//  kpop
//
//  Created by 呂 霄偉 on 2026/05/26.
//

import SwiftUI
import SwiftData

@main
struct kpopApp: App {
    private let modelContainer: ModelContainer
    private let jobsAPIClient: JobsAPIClient?

    init() {
        do {
            modelContainer = try ModelContainerFactory.make()
        } catch {
            fatalError("Failed to create SwiftData container: \(error)")
        }
        #if DEBUG
        jobsAPIClient = JobsAPIClient(
            configuration: JobsAPIConfiguration(
                baseURL: URL(string: "http://127.0.0.1:8000")!,
                bearerToken: "dev-user-a"
            )
        )
        #else
        jobsAPIClient = nil
        #endif
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(\.jobsAPIClient, jobsAPIClient)
        }
        .modelContainer(modelContainer)
    }
}
