import Foundation

// API는 테스트 응답으로 대체한다. 실제 설치나 사용자 설정 변경은 하지 않는다.
final class Feed: URLProtocol {
    static var payload = Data()
    static var status = 200
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.payload)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@main struct Tests {
    static var count = 0
    static func expect(_ value: @autoclosure () -> Bool, _ message: String) {
        precondition(value(), message); count += 1
    }
    static func wait(_ updates: Updates) {
        let deadline = Date().addingTimeInterval(5)
        while updates.state["phase"] as? String == "checking" && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
        expect(updates.state["phase"] as? String != "checking", "request completed")
    }
    static func feed(tag: String = "v2.4.0", digest: String? = "sha256:" + String(repeating: "a", count: 64), url: String? = nil, prerelease: Bool = false) -> Data {
        let version = String(tag.dropFirst())
        let asset: [String: Any] = ["name": "Spyhop-\(version).dmg", "browser_download_url": url ?? "\(Updates.releases)/download/\(tag)/Spyhop-\(version).dmg", "digest": digest as Any? ?? NSNull()]
        return try! JSONSerialization.data(withJSONObject: ["tag_name": tag, "draft": false, "prerelease": prerelease, "assets": [asset]])
    }
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("spyhop-model-tests-" + UUID().uuidString)
        let resources = root.appendingPathComponent("Spyhop.app/Contents/Resources")
        try FileManager.default.createDirectory(at: resources, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let info: [String: String] = ["CFBundleIdentifier": "spyhop.tests", "CFBundleShortVersionString": "2.3.0", "CFBundleExecutable": "Spyhop"]
        try PropertyListSerialization.data(fromPropertyList: info, format: .xml, options: 0).write(to: resources.deletingLastPathComponent().appendingPathComponent("Info.plist"))
        let rows = (1...4).map { Updates.Highlight(title: "Feature \($0)", detail: "Description") }
        let notes = Updates.Notes(newFeatures: rows, fixes: [Updates.Highlight(title: "A fix", detail: "Full description")])
        try JSONEncoder().encode(notes).write(to: resources.appendingPathComponent("whats-new.json"))
        let bundle = Bundle(url: resources.deletingLastPathComponent().deletingLastPathComponent())!
        let name = "spyhop.updates.tests." + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [Feed.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        func make() -> Updates {
            Updates(bundle: bundle, defaults: defaults, session: session,
                    stateFile: root.appendingPathComponent("state.json").path, home: root.path)
        }
        Feed.payload = feed()
        defaults.set("2.0.0", forKey: Updates.defaultsKey)
        let updates = make()
        updates.start()
        var foundByMenu = false
        updates.check(force: true) { foundByMenu = $0 }
        wait(updates)
        expect(foundByMenu, "menu check receives an in-flight result")
        expect(updates.state["phase"] as? String == "available", "new release offered")
        expect(updates.state["showChanges"] as? Bool == true, "skipped releases show current highlights")
        expect((updates.state["newFeatures"] as? [[String: String]])?.count == 4, "all new features retained")
        expect((updates.state["fixes"] as? [[String: String]])?.first?["detail"] == "Full description", "all fixes retained separately")
        let reopened = make()
        reopened.start(); wait(reopened)
        expect(reopened.state["showChanges"] as? Bool == true, "unacknowledged changes survive quit")
        reopened.dismissChanges()
        let same = make()
        same.start(); wait(same)
        expect(same.state["showChanges"] as? Bool == false, "acknowledged version stays dismissed")
        defaults.set("2.5.0", forKey: Updates.defaultsKey)
        let downgrade = make()
        downgrade.start(); wait(downgrade)
        expect(downgrade.state["showChanges"] as? Bool == false, "downgrade does not introduce features")
        Feed.payload = feed(tag: "v2.3.0")
        same.check(force: true); wait(same)
        expect(same.state["phase"] as? String == "current", "same version not offered")
        for invalid in [feed(tag: "v2.4.0-beta"), feed(digest: nil), feed(url: "https://example.com/update.dmg"), feed(prerelease: true)] {
            Feed.payload = invalid
            same.check(force: true); wait(same)
            expect(same.state["phase"] as? String == "error", "invalid release rejected")
        }
        Feed.status = 403
        same.check(force: true); wait(same)
        expect(same.state["phase"] as? String == "error", "API failure remains retryable")
        defaults.removePersistentDomain(forName: name)
        let fresh = make()
        fresh.start(); wait(fresh)
        expect(fresh.state["showChanges"] as? Bool == false, "fresh install does not show an update popup")
        print("\(count) update model assertions passed")
    }
}
