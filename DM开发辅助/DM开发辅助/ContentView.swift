import SwiftUI

struct ContentView: View {
    @State private var output: String = ""
    @State private var isRunning: Bool = false
    @State private var scriptProcess: Process?
    @State private var scriptDirectory: String = ""
    
    var body: some View {
        VStack(spacing: 16) {
            Text("DM开发辅助")
                .font(.largeTitle)
                .fontWeight(.bold)
                .padding(.top, 20)
            
            VStack(spacing: 10) {
                HStack(spacing: 12) {
                    ActionButton(title: "一键查询", color: .blue, isRunning: isRunning) {
                        runScript("check_services.sh")
                    }
                    ActionButton(title: "冒烟测试", color: .teal, isRunning: isRunning) {
                        runScript("smoke_test.sh")
                    }
                    ActionButton(title: "一键清除", color: .red, isRunning: isRunning) {
                        runScript("kill_services.sh")
                    }
                    ActionButton(title: "开发模式", color: .orange, isRunning: isRunning) {
                        runScript("open_dev_mode.sh")
                    }
                }
                HStack(spacing: 12) {
                    ActionButton(title: "一键打包", color: .purple, isRunning: isRunning) {
                        runScript("create_dmg.sh")
                    }
                    ActionButton(title: "一键备份", color: .green, isRunning: isRunning) {
                        runBackup()
                    }
                }
            }
            .padding(.horizontal)
            
            ScrollView {
                Text(output.isEmpty ? "等待执行命令..." : output)
                    .font(.system(.body, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
            }
            .background(Color.black.opacity(0.05))
            .cornerRadius(8)
            .padding(.horizontal)
            
            if isRunning {
                HStack {
                    ProgressView()
                    Text("正在执行命令...")
                        .foregroundColor(.secondary)
                }
                .padding()
            }
        }
        .frame(minWidth: 600, minHeight: 400)
        .onAppear {
            let bundleURL = Bundle.main.bundleURL
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
            scriptDirectory = bundleURL.path
            
            let fallbackURL = URL(fileURLWithPath: #file)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
            let fallbackDir = fallbackURL.path
            
            if FileManager.default.fileExists(atPath: fallbackDir + "/check_services.sh") {
                scriptDirectory = fallbackDir
            }
        }
    }
    
    func runScript(_ scriptName: String) {
        guard !isRunning else { return }
        
        let scriptPath = scriptDirectory + "/" + scriptName
        guard FileManager.default.fileExists(atPath: scriptPath) else {
            output = "错误: 找不到脚本 \(scriptName)\n路径: \(scriptPath)\n"
            return
        }
        
        isRunning = true
        output = "正在执行命令...\n\n"
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.currentDirectoryURL = URL(fileURLWithPath: scriptDirectory)
        process.arguments = ["-c", "bash \"\(scriptName)\" 2>&1"]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        
        let outHandle = pipe.fileHandleForReading
        outHandle.readabilityHandler = { handle in
            let data = handle.availableData
            if let string = String(data: data, encoding: .utf8), !string.isEmpty {
                DispatchQueue.main.async {
                    self.output += string
                }
            }
        }
        
        process.terminationHandler = { _ in
            DispatchQueue.main.async {
                self.isRunning = false
            }
        }
        
        do {
            try process.run()
            scriptProcess = process
        } catch {
            output += "错误: \(error.localizedDescription)\n"
            isRunning = false
        }
    }
    
    func runBackup() {
        guard !isRunning else { return }
        
        isRunning = true
        output = "正在备份项目（压缩包）...\n\n"
        
        let backupBase = "/Users/gengyun/Desktop/钻石记忆系统"
        let timestamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-").components(separatedBy: ".").first ?? "backup"
        let archiveName = "DiamondMemory-backup-" + timestamp + ".zip"
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = ["-c", """
        mkdir -p "\(backupBase)"
        ARCHIVE_PATH="\(backupBase)/\(archiveName)"
        
        PROJECT_DIR=""
        for candidate in \
            "\(scriptDirectory)" \
            "$(dirname "\(scriptDirectory)")/DiamondMemory" \
            "/Users/gengyun/Desktop/DiamondMemory"; do
            if [ -d "$candidate/frontend" ] && [ -d "$candidate/backend" ]; then
                PROJECT_DIR="$candidate"
                break
            fi
        done
        
        if [ -z "$PROJECT_DIR" ]; then
            echo "❌ 备份失败：找不到项目目录（需包含 frontend 和 backend 文件夹）"
            echo "当前搜索路径："
            echo "  1. \(scriptDirectory)"
            echo "  2. \(scriptDirectory)/../DiamondMemory"
            echo "  3. /Users/gengyun/Desktop/DiamondMemory"
            exit 1
        fi
        
        echo "📂 项目目录: $PROJECT_DIR"
        
        cd "$PROJECT_DIR"
        
        zip -r "$ARCHIVE_PATH" frontend backend -x "node_modules/*" -x ".git/*" -x "dist/*" -x "__pycache__/*" -x ".nuitka/*" -x "*.pyc" -x ".DS_Store" -x "frontend/node_modules/*" -x "frontend/dist/*" -x "backend/__pycache__/*" 2>&1
        
        for f in package.json README.md PROJECT_OPERATIONS.md; do
            if [ -f "$PROJECT_DIR/$f" ]; then
                zip -u "$ARCHIVE_PATH" "$f" 2>/dev/null
            fi
        done
        
        if [ -f "$ARCHIVE_PATH" ]; then
            ARCHIVE_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
            echo ""
            echo "🎉 备份完成！"
            echo "📦 压缩包: \(archiveName)"
            echo "📏 大小: $ARCHIVE_SIZE"
            echo "📂 保存至: \(backupBase)/"
        else
            echo ""
            echo "❌ 备份失败：未能创建压缩包"
        fi
        
        BACKUP_COUNT=$(ls -1 "\(backupBase)"/DiamondMemory-backup-*.zip 2>/dev/null | wc -l | tr -d ' ')
        if [ "$BACKUP_COUNT" -gt 10 ]; then
            echo ""
            echo "🧹 清理旧备份（保留最近10个）..."
            ls -1t "\(backupBase)"/DiamondMemory-backup-*.zip | tail -n +11 | xargs rm -f
            echo "✅ 清理完成"
        fi
        """]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        
        let outHandle = pipe.fileHandleForReading
        outHandle.readabilityHandler = { handle in
            let data = handle.availableData
            if let string = String(data: data, encoding: .utf8), !string.isEmpty {
                DispatchQueue.main.async {
                    self.output += string
                }
            }
        }
        
        process.terminationHandler = { _ in
            DispatchQueue.main.async {
                self.isRunning = false
            }
        }
        
        do {
            try process.run()
            scriptProcess = process
        } catch {
            output += "错误: \(error.localizedDescription)\n"
            isRunning = false
        }
    }
}

struct ActionButton: View {
    let title: String
    let color: Color
    let isRunning: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(title)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(isRunning ? color.opacity(0.5) : color)
                .foregroundColor(.white)
                .cornerRadius(8)
        }
        .disabled(isRunning)
    }
}
