# Agent Learning API

一个使用 FastAPI 构建的最小 API 服务。目前只包含健康检查接口。

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## 安装依赖

```bash
uv sync
```

## 启动服务

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

服务启动后可访问：

- 健康检查：<http://127.0.0.1:8000/health>
- API 文档：<http://127.0.0.1:8000/docs>
- test检查：<http://127.0.0.1:8000/test>

健康检查响应：

```json
{
  "status": "ok",
  "service": "agent-learning-api"
}
```
test检查：

```json
{
  "message": "hhy is pig",
}
```