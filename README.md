# Agent Learning API

一个使用 FastAPI 构建的学习型 API 服务。目前支持健康检查，以及使用内存存储创建和查询学习任务。

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
- 测试接口：<http://127.0.0.1:8000/test>

## API 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 检查服务是否正常运行 |
| `POST` | `/tasks` | 创建任务，成功时返回 201 |
| `GET` | `/tasks` | 查询任务列表 |
| `GET` | `/tasks/{task_id}` | 根据 ID 查询单个任务，不存在时返回 404 |

### 创建任务

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "学习 FastAPI",
    "description": "完成任务创建与查询接口",
    "status": "todo",
    "priority": 1,
    "estimated_minutes": 60
  }'
```

响应示例：

```json
{
  "id": 1,
  "title": "学习 FastAPI",
  "description": "完成任务创建与查询接口",
  "status": "todo",
  "priority": 1,
  "estimated_minutes": 60,
  "created_at": "2026-09-13T08:00:00Z"
}
```

输入数据需要满足以下规则：

- `title` 不能为空或只包含空白字符。
- `status` 只能是 `todo`、`doing` 或 `done`，默认值为 `todo`。
- `priority` 只能是 `1`、`2` 或 `3`，默认值为 `2`。
- `estimated_minutes` 必须是大于 0 的整数。
- `description` 未提供时默认为空字符串。

### 查询任务

查询全部任务：

```bash
curl http://127.0.0.1:8000/tasks
```

查询 ID 为 1 的任务：

```bash
curl http://127.0.0.1:8000/tasks/1
```

## 内存存储说明

当前任务保存在 Python 列表中，没有接入数据库。任务数据只存在于运行服务的进程内，服务停止或重启后会全部消失。

## 运行测试

```bash
uv run pytest -q
```

## 现有辅助接口

健康检查响应：

```json
{
  "status": "ok",
  "service": "agent-learning-api"
}
```

测试接口响应：

```json
{
  "message": "hhy is pig"
}
```
