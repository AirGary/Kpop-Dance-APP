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
    private let uploadRunner: UploadRunner?

    init() {
        do {
            modelContainer = try ModelContainerFactory.make()
        } catch {
            fatalError("Failed to create SwiftData container: \(error)")
        }
        #if DEBUG
        let configuration = JobsAPIConfiguration(
            baseURL: URL(string: "http://127.0.0.1:8000")!,
            bearerToken: "dev-user-a"
        )
        jobsAPIClient = JobsAPIClient(configuration: configuration)
        uploadRunner = try? UploadRunner(
            coordinator: ResumableUploadCoordinator.live(configuration: configuration)
        )
        #else
        jobsAPIClient = nil
        uploadRunner = nil
        #endif
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(\.jobsAPIClient, jobsAPIClient)
                .environment(\.uploadRunner, uploadRunner)
        }
        .modelContainer(modelContainer)
    }
}
