# AstrBot 一键开发模式启动脚本（本地定制，不属于上游）
# 后端: uv run main.py      -> http://localhost:6185
# 前端: dashboard/pnpm dev  -> http://localhost:3000 (API 代理到 6185)
$root = $PSScriptRoot

# 启动后端（独立窗口，日志实时可见）
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root'; uv run main.py"

# 启动前端（独立窗口）
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\dashboard'; pnpm dev"

# 等待服务就绪后自动打开浏览器（前端开发服务器）
Start-Sleep -Seconds 20
Start-Process 'http://localhost:3000'
