// swift-tools-version:6.0
// A tiny app with a widget, so the tests of swift-app-bundler have something real to bundle.
import PackageDescription

let package = Package(
    name: "SampleApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "SampleApp"),
        .executableTarget(name: "SampleWidget"),
    ]
)
