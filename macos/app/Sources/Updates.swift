import Foundation
import CryptoKit

/// 업데이트 메타데이터와 설치. 화면 및 앱 종료는 호출자가 맡는다.
final class Updates {
    static let shared = Updates()
    static let releases = "https://github.com/leeleelee3264/spyhop/releases"
    static let feed = URL(string: "https://api.github.com/repos/leeleelee3264/spyhop/releases/latest")!
    static let defaultsKey = "lastLaunchedVersion"
    struct Release: Decodable {
        struct Asset: Decodable {
            let name: String
            let browser_download_url: String
            let digest: String?
        }
        let tag_name: String
        let draft: Bool
        let prerelease: Bool
        let assets: [Asset]
        var version: String { String(tag_name.dropFirst()) }
        var asset: Asset? { assets.first { $0.name == "Spyhop-\(version).dmg" } }
        var valid: Bool {
            tag_name.range(of: #"^v\d+\.\d+\.\d+$"#, options: .regularExpression) != nil && !draft && !prerelease
        }
        var downloadable: Bool {
            guard valid, let a = asset, let digest = a.digest else { return false }
            return a.browser_download_url == "\(Updates.releases)/download/\(tag_name)/\(a.name)"
                && digest.range(of: #"^sha256:[a-f0-9]{64}$"#, options: .regularExpression) != nil
        }
    }
    struct Highlight: Codable { let title: String; let detail: String }
    struct Notes: Codable {
        let newFeatures: [Highlight]
        let fixes: [Highlight]
        var isEmpty: Bool { newFeatures.isEmpty && fixes.isEmpty }
    }
    enum Failure: LocalizedError {
        case message(String)
        var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
    }

    private let bundle: Bundle
    private let defaults: UserDefaults
    private let session: URLSession
    private let stateFile: String
    private let home: String
    private let queue = DispatchQueue(label: "spyhop.updates")
    private(set) var release: Release?
    private var phase = "idle"
    private var error = ""
    private var showChanges = false
    private var notes = Notes(newFeatures: [], fixes: [])
    private var checkAt = Date.distantPast
    private var checkCompletions: [(Bool) -> Void] = []
    var changed: (() -> Void)?
    var restart: (() -> Void)?
    var version: String { bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "dev" }

    init(bundle: Bundle = .main, defaults: UserDefaults = .standard, session: URLSession = .shared,
         stateFile: String = Board.stateFile, home: String = Board.home) {
        self.bundle = bundle; self.defaults = defaults; self.session = session
        self.stateFile = stateFile; self.home = home
    }

    /// 첫 설치에는 띄우지 않고, 실제 버전 상승 때만 현재 번들의 설명을 한 번 보여준다.
    func start() {
        let previous = defaults.string(forKey: Self.defaultsKey)
        if let url = bundle.url(forResource: "whats-new", withExtension: "json"),
           let data = try? Data(contentsOf: url), let loaded = try? JSONDecoder().decode(Notes.self, from: data) {
            notes = loaded
        }
        // 예전 앱에는 defaults 기록이 없으므로 보드가 남긴 실행 버전을 이관한다.
        let state = (try? Data(contentsOf: URL(fileURLWithPath: stateFile)))
            .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
        let old = previous ?? state?["version"] as? String
        if let old, old != "dev", Board.newer(version, than: old), !notes.isEmpty {
            defaults.set(version, forKey: "pendingWhatsNew")
        }
        showChanges = defaults.string(forKey: "pendingWhatsNew") == version && !notes.isEmpty
        defaults.set(version, forKey: Self.defaultsKey)
        let result = URL(fileURLWithPath: home + "/update-result.json")
        if let data = try? Data(contentsOf: result), let record = try? JSONSerialization.jsonObject(with: data) as? [String: String] {
            error = record["error"] ?? ""
            if !error.isEmpty { phase = "error" }
            try? FileManager.default.removeItem(at: result)
        }
        check()
    }

    var state: [String: Any] {
        ["phase": phase, "version": version, "latest": release?.version ?? "", "error": error,
         "showChanges": showChanges,
         "newFeatures": notes.newFeatures.map { ["title": $0.title, "detail": $0.detail] },
         "fixes": notes.fixes.map { ["title": $0.title, "detail": $0.detail] }]
    }

    func dismissChanges() {
        showChanges = false
        defaults.removeObject(forKey: "pendingWhatsNew")
        changed?()
    }

    func check(force: Bool = false, completion: ((Bool) -> Void)? = nil) {
        guard phase != "installing" else { return }
        if let completion { checkCompletions.append(completion) }
        guard phase != "checking", force || Date().timeIntervalSince(checkAt) > 3600 else { return }
        checkAt = Date()
        phase = "checking"; changed?()
        var request = URLRequest(url: Self.feed, timeoutInterval: 20)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("Spyhop/\(version)", forHTTPHeaderField: "User-Agent")
        session.dataTask(with: request) { data, response, failure in
            let found = data.flatMap { try? JSONDecoder().decode(Release.self, from: $0) }
            DispatchQueue.main.async {
                guard failure == nil, (response as? HTTPURLResponse)?.statusCode == 200,
                      let found, found.downloadable else {
                    // 외부 조회 실패는 자동 검사에서는 조용히 둔다. 수동 검사에서만 설명한다.
                    self.phase = self.release == nil ? "idle" : "available"
                    if force || !self.checkCompletions.isEmpty { self.error = "Could not check for updates. Please try again."; self.phase = "error" }
                    self.changed?(); self.finishCheck(available: false); return
                }
                self.release = Board.newer(found.version, than: self.version) ? found : nil
                self.error = ""; self.phase = self.release == nil ? "current" : "available"
                self.changed?()
                self.finishCheck(available: self.release != nil)
            }
        }.resume()
    }

    private func finishCheck(available: Bool) {
        let callbacks = checkCompletions
        checkCompletions.removeAll()
        callbacks.forEach { $0(available) }
    }

    func install() {
        guard let release, phase != "installing", release.downloadable else { return }
        phase = "installing"; error = ""; changed?()
        queue.async {
            do {
                let helper = try self.prepare(release)
                DispatchQueue.main.async {
                    do {
                        try helper.run()
                        self.restart?()
                    } catch { self.fail("Could not start the installer. Please try again.") }
                }
            } catch { DispatchQueue.main.async { self.fail(error.localizedDescription) } }
        }
    }

    private func fail(_ message: String) { error = message; phase = "error"; changed?() }

    /// Cask 설치 기록을 유지하기 위해 관리 중인 앱은 brew로 업데이트한다.
    private func brewInstall() -> String? {
        for prefix in ["/opt/homebrew", "/usr/local"] {
            if FileManager.default.fileExists(atPath: prefix + "/Caskroom/spyhop") { return prefix + "/bin/brew" }
        }
        return nil
    }

    private func prepare(_ release: Release) throws -> Process {
        let fm = FileManager.default
        let app = bundle.bundleURL.standardizedFileURL
        guard !app.path.contains("/AppTranslocation/"), !app.path.hasPrefix("/Volumes/"),
              app.pathExtension == "app", fm.isWritableFile(atPath: app.deletingLastPathComponent().path),
              fm.isWritableFile(atPath: app.path) else {
            throw Failure.message("Move Spyhop to a writable Applications folder, then try again.")
        }
        let work = fm.temporaryDirectory.appendingPathComponent("spyhop-update-" + UUID().uuidString)
        try fm.createDirectory(at: work, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        var handedOff = false
        defer { if !handedOff { try? fm.removeItem(at: work) } }
        guard let source = bundle.url(forResource: "install-update", withExtension: "py") else {
            throw Failure.message("The installer is missing. Reinstall Spyhop from its release page.")
        }
        let script = work.appendingPathComponent("install.py")
        try fm.copyItem(at: source, to: script)
        var args = [script.path, "--pid", String(ProcessInfo.processInfo.processIdentifier), "--app", app.path,
                    "--version", release.version, "--from-version", version, "--result", home + "/update-result.json"]
        if let brew = brewInstall() {
            // 다른 위치의 DMG 사본에서 Cask 설치본을 덮어쓰지 않는다.
            let info = try command(brew, ["info", "--json=v2", "--cask", "spyhop"])
            guard let data = info.data(using: .utf8), let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let casks = json["casks"] as? [[String: Any]], let cask = casks.first,
                  cask["full_token"] as? String == "leeleelee3264/tap/spyhop",
                  let artifacts = cask["artifacts"] as? [[String: Any]],
                  artifacts.contains(where: { row in
                      guard row["app"] != nil, let target = row["target"] as? String else { return false }
                      return URL(fileURLWithPath: target).standardizedFileURL == app
                  }) else {
                throw Failure.message("Another Homebrew installation of Spyhop was found. Open that copy to update it, or remove it before updating this copy.")
            }
            _ = try command(brew, ["update"])
            let latest = try command(brew, ["info", "--json=v2", "--cask", "leeleelee3264/tap/spyhop"])
            guard let data = latest.data(using: .utf8), let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let casks = json["casks"] as? [[String: Any]], let cask = casks.first,
                  cask["version"] as? String == release.version,
                  cask["url"] as? String == release.asset?.browser_download_url,
                  cask["sha256"] as? String == release.asset?.digest?.replacingOccurrences(of: "sha256:", with: "") else {
                throw Failure.message("This release is not available on Homebrew yet. Please try again later.")
            }
            args += ["--brew", brew]
        } else {
            let dmg = work.appendingPathComponent("update.dmg")
            try download(release.asset!, to: dmg)
            let mount = work.appendingPathComponent("mount")
            _ = try command("/usr/bin/hdiutil", ["attach", "-nobrowse", "-readonly", "-mountpoint", mount.path, dmg.path])
            defer { _ = try? command("/usr/bin/hdiutil", ["detach", mount.path]) }
            let staged = work.appendingPathComponent("Spyhop.app")
            _ = try command("/usr/bin/ditto", [mount.appendingPathComponent("Spyhop.app").path, staged.path])
            try Self.validateApp(staged, version: release.version)
            // 배포 Cask와 같은 처리. 해시와 서명을 검증한 뒤에만 격리를 해제한다.
            _ = try command("/usr/bin/xattr", ["-dr", "com.apple.quarantine", staged.path])
            args += ["--staged", staged.path]
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = args
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        process.environment = env
        handedOff = true
        return process
    }

    private func download(_ asset: Release.Asset, to destination: URL) throws {
        let done = DispatchSemaphore(value: 0)
        var failure: Error?
        let task = session.downloadTask(with: URLRequest(url: URL(string: asset.browser_download_url)!, timeoutInterval: 180)) { local, response, error in
            defer { done.signal() }
            do {
                guard error == nil, let local, (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw Failure.message("Download failed. Check your connection and try again.")
                }
                let data = try Data(contentsOf: local, options: .mappedIfSafe)
                let digest = "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                guard digest == asset.digest else { throw Failure.message("The download could not be verified. Please try again.") }
                try FileManager.default.moveItem(at: local, to: destination)
            } catch { failure = error }
        }
        task.resume()
        guard done.wait(timeout: .now() + 200) == .success else {
            task.cancel(); done.wait()
            throw Failure.message("The download timed out. Please try again.")
        }
        if let failure { throw failure }
    }

    static func validateApp(_ app: URL, version: String) throws {
        guard let bundle = Bundle(url: app), bundle.bundleIdentifier == "io.github.leeleelee3264.spyhop",
              bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String == version,
              let executable = bundle.executableURL, FileManager.default.isExecutableFile(atPath: executable.path),
              Board.run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app.path]) == 0 else {
            throw Failure.message("The new app could not be verified. Your current app has been kept.")
        }
    }

    private func command(_ path: String, _ args: [String]) throws -> String {
        let process = Process(), out = Pipe()
        process.executableURL = URL(fileURLWithPath: path); process.arguments = args
        process.standardOutput = out; process.standardError = FileHandle.nullDevice
        var env = ProcessInfo.processInfo.environment
        env["HOMEBREW_NO_AUTO_UPDATE"] = "1"; env["HOMEBREW_NO_ENV_HINTS"] = "1"
        process.environment = env
        try process.run()
        // 파이프를 읽으며 기다려 출력이 막히지 않게 한다. 긴 brew 처리에도 기한을 둔다.
        let timeout = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 180, execute: timeout)
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit(); timeout.cancel()
        guard process.terminationStatus == 0 else { throw Failure.message("Could not prepare the update. Please try again or update Spyhop with Homebrew.") }
        return String(decoding: data, as: UTF8.self)
    }
}
