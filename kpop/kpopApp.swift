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
    private let analysisAPIClient: AnalysisAPIClient?
    private let analysisService: (any AnalysisService)?

    init() {
        do {
            modelContainer = try ModelContainerFactory.make()
        } catch {
            fatalError("Failed to create SwiftData container: \(error)")
        }
#if DEBUG
        var launchInfo = Bundle.main.infoDictionary ?? [:]
        let processInfo = ProcessInfo.processInfo.environment
        if let environment = processInfo["STAGE_LAB_ENVIRONMENT"] {
            launchInfo["STAGE_LAB_ENVIRONMENT"] = environment
        }
        if let baseURL = processInfo["STAGE_LAB_API_BASE_URL"] {
            launchInfo["STAGE_LAB_API_BASE_URL"] = baseURL
        }
        if let pairingToken = processInfo["STAGE_LAB_PAIRING_TOKEN"] {
            launchInfo["STAGE_LAB_PAIRING_TOKEN"] = pairingToken
        }
        let configuration: JobsAPIConfiguration
        if let configured = try? JobsAPIConfiguration.from(infoDictionary: launchInfo), let configured {
            configuration = configured
        } else {
            configuration = JobsAPIConfiguration(
                baseURL: URL(string: "http://127.0.0.1:8000")!,
                bearerToken: "dev-user-a"
            )
        }
        jobsAPIClient = JobsAPIClient(configuration: configuration)
        let configuredAnalysisClient = AnalysisAPIClient(configuration: configuration)
        analysisAPIClient = configuredAnalysisClient
        analysisService = RemoteAnalysisService(client: configuredAnalysisClient)
        uploadRunner = try? UploadRunner(
            coordinator: ResumableUploadCoordinator.live(configuration: configuration)
        )
        #else
        jobsAPIClient = nil
        uploadRunner = nil
        analysisAPIClient = nil
        analysisService = nil
        #endif
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(\.jobsAPIClient, jobsAPIClient)
                .environment(\.uploadRunner, uploadRunner)
                .environment(\.analysisAPIClient, analysisAPIClient)
                .environment(\.analysisService, analysisService)
        }
        .modelContainer(modelContainer)
    }
}
