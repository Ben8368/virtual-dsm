# 安全边界

- 不在 Git 中提交 DSM PAT、账户密码、会话 cookie、磁盘镜像或完整串口转储。
- 研究证据与 disposable 凭据留在忽略目录；公开文档只保留路径与非秘密元数据。
- 生产镜像构建不得掺入未晋升的研究 QEMU 补丁。
- 最小化对外暴露：管理端口默认绑定策略以平台文档为准；不要为调试永久放开 `docker.sock` 权限。
- 安全问题请通过 GitHub private vulnerability reporting 或维护者私信联系；不要在公开 issue 粘贴密钥。

当前阶段与能力状态以 [CONTEXT.md](CONTEXT.md) 为准，不在本文件复制 Phase 结论。
