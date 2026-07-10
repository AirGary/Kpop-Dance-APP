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

    init() {
        do {
            modelContainer = try ModelContainerFactory.make()
        } catch {
            fatalError("Failed to create SwiftData container: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
        .modelContainer(modelContainer)
    }
}
