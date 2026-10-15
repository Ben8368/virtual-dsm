# Lesson：Windows / WSL / Docker

- 文件保持 UTF-8 LF；PowerShell 下注意 CRLF 污染补丁与 hook 消息。
- WSL Docker 需要用户在 `docker` 组；可用 `wsl -u root usermod -aG docker <user>` 后 `wsl --shutdown`，不要 `chmod 666` docker.sock。
- 中文输出在 Windows 终端可能乱码；以 UTF-8 文件与 CI Linux 结果为准。
