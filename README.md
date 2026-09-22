# Agent Learning API

一个使用 FastAPI 构建的学习型 API 服务。目前支持健康检查，以及使用 MySQL 持久化创建、查询、修改和删除学习任务。

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Compose（运行 MySQL）

## 安装依赖

```bash
uv sync
```

## 配置和启动 MySQL

复制示例环境变量，并为 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` 设置不同的密码；将 `DATABASE_URL` 中的用户名、密码、端口和库名与 MySQL 配置保持一致。密码若含 `@`、`:`、`/` 等字符，需在 URL 中进行百分号编码。`.env` 已加入 `.gitignore`，不要提交密码。

```bash
cp .env.example .env
docker compose up -d mysql
docker compose ps
```

已有 `.env` 和 MySQL 卷时，只需补充 `DATABASE_URL`，无需重建或清空卷。`DATABASE_URL` 必须是 `mysql+pymysql://...` 格式。数据库结构由 Alembic 管理，应用启动时不会自动建表；首次启动应用前先执行迁移。

## 数据库迁移

所有 Alembic 命令都通过 `.env` 读取与应用相同的 `DATABASE_URL`。全新数据库升级到最新结构：

```bash
uv run --env-file .env alembic upgrade head
```

查看当前 revision 和迁移历史：
```bash
uv run --env-file .env alembic heads
```
current 查看数据库当前所在的 revision，heads 查看迁移代码中的最新 revision。


```bash
uv run --env-file .env alembic current
uv run --env-file .env alembic history --verbose
```

修改 SQLAlchemy Model 后，自动生成迁移并检查是否还有未生成的差异：

```bash
uv run --env-file .env alembic revision --autogenerate -m "describe schema change"
# 执行前必须人工阅读 alembic/versions/ 下新生成的迁移文件
uv run --env-file .env alembic check
```

执行升级，或回退一个 revision：

```bash
uv run --env-file .env alembic upgrade head
uv run --env-file .env alembic downgrade -1
```

如果数据库已由旧版本应用的 `Base.metadata.create_all()` 建好，且结构经核对与初始迁移完全一致，可只对该现有数据库标记基线，再执行后续迁移：

```bash
uv run --env-file .env alembic stamp 8771c71d067b
uv run --env-file .env alembic upgrade head
```

`stamp` 只写入 revision，不执行建表；不能用于空数据库，也不能代替结构核对。生产环境执行 `downgrade` 前应先备份数据，因为回退字段或表会丢弃其中的数据。

## 启动服务

```bash
uv run uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
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
| `PATCH` | `/tasks/{task_id}` | 部分更新任务，不存在时返回 404 |
| `DELETE` | `/tasks/{task_id}` | 删除任务，成功时返回 204，不存在时返回 404 |

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
  "created_at": "2026-09-13T08:00:00Z",
  "updated_at": "2026-09-13T08:00:00Z"
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

### 修改和删除任务

只提交需要修改的字段：

```bash
curl -X PATCH http://127.0.0.1:8000/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "doing"}'
```

修改时会刷新 `updated_at`。已完成（`done`）的任务不能直接改回 `todo`，此时返回 409。

删除任务：

```bash
curl -X DELETE http://127.0.0.1:8000/tasks/1
```

删除成功返回 204，响应体为空。

## 数据库存储说明

任务保存在 MySQL `tasks` 表中，服务重启后仍可查询。`app/models.py` 定义数据库 Model；`app/main.py` 中的 Pydantic Schema 负责请求校验和响应格式。每个请求获取独立的 SQLAlchemy Session，请求结束后关闭；创建、修改和删除会提交事务，发生异常时回滚。`/health` 不检查数据库连接。

可直接在数据库中核对记录：

```bash
docker compose exec mysql sh -c 'mysql --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" --database="$MYSQL_DATABASE" --execute="SELECT id, title, status FROM tasks ORDER BY id DESC LIMIT 5;"'
```

## 运行测试

```bash
uv run pytest -q
```

测试为每个用例创建独立的临时 SQLite 数据库，并替换 Session 工厂，不会删除 MySQL 数据。原先依赖内存列表 `tasks.clear()` 的用例已改为这种数据库隔离方式；运行中的 MySQL 持久性还需用实际服务重启验证。

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
