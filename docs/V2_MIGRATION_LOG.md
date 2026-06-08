# V2 迁移记录

## 基线信息

- V1 冻结提交：`d8a4d5646e10034b46739b6e79849b16d304aed1`
- V1 标签：`v0.1-demo`
- 稳定目录：`D:\Project\GitLearnAgent`
- V2 worktree：`D:\Project\GitLearnAgent-v2`
- V2 分支：`v2-development`
- 远程分支：`GitLearnAgent/v2-development`
- 记录日期：2026-06-07

## 当前基线测试结果

已执行：

```powershell
cd backend
D:\Programme\Anaconda\envs\gitlearnagent\python.exe -B -m unittest discover tests
```

结果：

```text
Ran 8 tests in 0.002s

OK
```

补充说明：当前 shell 中 `python` 不在 PATH，直接执行 `python -B -m unittest discover tests` 失败；使用现有启动脚本中约定的 Conda Python 路径后，后端测试通过。

## 已知问题

- 根目录 `start_all.bat` 在当前 V2 worktree 中仍硬编码调用 `D:\Project\GitLearnAgent` 下的后端和前端脚本。
- `backend/run_backend.bat`、`backend/run_backend.ps1`、`frontend/run_frontend.bat`、`frontend/run_frontend.ps1` 存在本机 Conda 路径假设。
- `backend/app/services/github_client.py` 的 GitHub Token 错误提示中硬编码了 V1 目录下的 `.env` 路径。
- 当前问答引用没有行号。
- 当前 Python AST 分析没有保存函数/类代码块内容、起止行号或内容哈希。
- 当前检索没有 BGE-M3、向量库或 Embedding 缓存。
- 当前 LLM 输出没有 Schema 校验和可追踪重试记录。
- 当前数据库没有迁移框架和 schema 版本管理。

## 尚未迁移或替换的旧功能

- 文件级静态分析仍需升级为函数/类代码块分析。
- 文件级核心排序仍需补充代码块级排序和证据验证。
- 规则检索仍需升级为关键词与语义混合检索。
- 本地规则学习路线仍需升级为诊断驱动的动态学习路径。
- Markdown 报告仍需升级为包含学习过程、证据和评分细则的学习档案。
- 前端仍是 V1 标签页式工作台，尚未迁移为引导式三栏学习工作台。

## 迁移记录模板

后续每次迁移或模块替换时追加一条记录。

```markdown
## YYYY-MM-DD 模块名称

- 日期：
- 模块：
- 功能分支：
- 修改摘要：
- 数据库变化：
- 配置变化：
- 测试命令：
- 测试结果：
- 已知限制：
- 提交 SHA：
```

## 初始记录

### 2026-06-07 V2 开发规范和规划文档

- 日期：2026-06-07
- 模块：开发规范、V1 基线、V2 规划、迁移记录
- 功能分支：`v2-development`
- 修改摘要：初始化 V2 文档，不实现业务功能。
- 数据库变化：无。
- 配置变化：无。
- 测试命令：`D:\Programme\Anaconda\envs\gitlearnagent\python.exe -B -m unittest discover tests`
- 测试结果：8 个后端 unittest 通过。
- 已知限制：前端构建未执行；当前未修改前端业务代码，且禁止安装新依赖。
- 提交 SHA：待提交后补充。

### 2026-06-08 Python 函数级代码块

- 日期：2026-06-08
- 模块：Python 函数级代码块
- 功能分支：`feat/python-code-chunks`
- 修改摘要：新增独立 Python AST 代码块提取模块，支持函数、异步函数、类、方法、异步方法、嵌套符号、装饰器起始行、多行签名、CRLF、非 ASCII 内容和语法错误警告；在仓库分析成功路径中对 `.py` 文件提取代码块并保存。
- 数据库变化：新增 `schema_versions` 表记录轻量 schema 版本；新增 `code_chunks` 表，保存项目外键、仓库 revision、语言、路径、代码块类型、符号名、限定名、父符号、起止行号、原始内容、SHA-256 内容哈希和创建时间；新增项目级保存、文件级替换、按项目/路径/符号/类型查询和项目删除清理接口。当前仍使用幂等 SQLite 初始化，后续可引入正式迁移工具。
- 配置变化：无。
- 测试命令：`D:\Programme\Anaconda\envs\gitlearnagent\python.exe -B -m unittest tests.test_code_chunker tests.test_database_code_chunks`；`D:\Programme\Anaconda\envs\gitlearnagent\python.exe -B -m unittest discover tests`
- 测试结果：最小相关测试 16 个通过；完整后端 unittest 24 个通过。
- 已知限制：仅处理 Python AST 可静态定位的函数和类定义；不分析动态生成符号；未生成 Embedding，未实现混合检索或 RAG；前端暂不展示代码块。
- 提交 SHA：待提交。
