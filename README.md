# GitLearnAgent

GitLearnAgent 是一个面向编程初学者的 GitHub 开源项目学习 Agent。它不是把仓库链接直接丢给大模型做摘要，而是先抓取公开仓库、过滤源码文件、做静态分析和文件重要性排序，再生成项目地图、学习路线、源码溯源问答和 Markdown 报告。

## 功能

- 输入公开 GitHub 仓库 URL，自动分析 Python、JavaScript、TypeScript 项目。
- 识别 README、依赖文件、入口文件、核心模块和可能的启动命令。
- 生成项目概览、目录树、模块职责、学习路线、任务卡和测验。
- 源码问答先检索相关文件，再输出带引用路径的回答。
- 大模型接口可选；没有 `LLM_API_KEY` 时仍可完成静态分析和规则问答。

## 一键启动

```powershell
D:\Project\GitLearnAgent\start_all.bat
```

这个脚本会打开两个窗口：一个运行后端，一个运行前端。使用时两个窗口都不要关。

## 别人克隆后如何运行

```powershell
git clone <你的仓库地址>
cd GitLearnAgent
conda env create -f environment.yml
conda activate gitlearnagent
copy .env.example .env
notepad .env
```

在 `.env` 中填入自己的 `GITHUB_TOKEN` 后：

```powershell
backend\run_backend.bat
frontend\run_frontend.bat
```

如果不用 conda，也可以自己安装 Python 3.12 和 Node.js，然后分别执行 `pip install -r backend\requirements.txt` 与 `npm install`。

## 项目结构

```text
GitLearnAgent/
  backend/   FastAPI API、GitHub 抓取、静态分析、学习路线、问答、报告
  frontend/  React + TypeScript + Vite 工作台
  docs/      大创申报、技术路线、实验设计
  samples/   演示仓库清单
```

## 后端运行

## GitHub 限流配置

如果看到 `API rate limit exceeded`，说明当前公网 IP 的 GitHub 匿名请求次数用完了。创建一个 GitHub token 后，在 `D:\Project\GitLearnAgent\.env` 写入：

```text
GITHUB_TOKEN=你的 GitHub Token
```

保存后重启后端。可以打开 `http://127.0.0.1:8000/api/health`，确认 `github_token_configured` 为 `true`。

如果你已经按当前配置创建了 conda 环境：

```powershell
conda activate gitlearnagent
cd D:\Project\GitLearnAgent\backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

本机也已经提供脚本：

```powershell
D:\Project\GitLearnAgent\backend\run_backend.ps1
```

如果 PowerShell 禁止运行 `.ps1`，直接运行：

```powershell
D:\Project\GitLearnAgent\backend\run_backend.bat
```

通用虚拟环境方式：

```powershell
cd D:\Project\GitLearnAgent\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_API_KEY="你的 API Key"
$env:LLM_MODEL="deepseek-chat"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

没有 API key 也可以运行，只是部分自然语言增强会走本地规则兜底。

## 前端运行

如果已经激活 `gitlearnagent`：

```powershell
cd D:\Project\GitLearnAgent\frontend
npm install
npm run dev
```

本机也已经提供脚本：

```powershell
D:\Project\GitLearnAgent\frontend\run_frontend.ps1
```

如果 PowerShell 禁止运行 `.ps1`，直接运行：

```powershell
D:\Project\GitLearnAgent\frontend\run_frontend.bat
```

浏览器打开 `http://127.0.0.1:5173`。

## API

- `POST /api/projects/analyze`：提交仓库 URL，返回 `project_id`。
- `GET /api/projects/{project_id}`：项目概览、技术栈、核心文件。
- `GET /api/projects/{project_id}/map`：目录树、模块关系、核心文件。
- `GET /api/projects/{project_id}/learning-path`：学习路线、任务和测验。
- `POST /api/projects/{project_id}/ask`：源码问答，返回答案和引用。
- `GET /api/projects/{project_id}/report`：Markdown 分析报告。

## 大创差异化

直接问通用 AI 时，模型往往只依据 README 或少量上下文回答，容易漏掉入口文件、依赖配置和真实模块边界。GitLearnAgent 的差异点是：

- 先做确定性静态分析，再让 AI 参与表达和教学组织。
- 输出学习路径、任务卡和测验，而不是一次性摘要。
- 问答必须附带源码路径和片段引用，降低幻觉。
- 支持对比实验，可以量化模块覆盖率、引用准确率和初学者友好度。
