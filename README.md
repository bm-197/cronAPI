# CronAPI - Modular Job Scheduler with REST API

CronAPI is a modern, distributed job scheduler with a REST API interface that combines the flexibility of cron expressions with the power of a modular, API-first architecture. It's designed to be both simple to use and powerful enough for complex scheduling needs.

## Key Features

### 1. REST API-First Design
- **Full API Control**: Unlike traditional job schedulers, every aspect of job management is accessible via REST API
- **Swagger/OpenAPI Documentation**: Auto-generated API documentation for easy integration
- **Language Agnostic**: Schedule and manage jobs from any programming language or tool that can make HTTP requests

### 2. Advanced Job Management
- **Dynamic Job Definitions**: Jobs can be added, modified, or removed without restarting the service
- **Job Dependencies**: Define job dependencies to create complex workflows
- **Success/Failure Chaining**: Automatically trigger specific jobs on success or failure of other jobs
- **Parameter Schema Validation**: Define and validate job parameters using JSON Schema
- **Comprehensive Job Logs**: Detailed execution history with timing and error information

### 3. Distributed Architecture
- **Leader Election**: Built-in leader election ensures only one instance runs each job
- **Multi-Instance Support**: Run multiple instances for high availability
- **Instance Awareness**: Track which instance is running each job
- **Redis Support**: Optional Redis backend for distributed state management

### 4. Security and Access Control
- **Role-Based Access Control**: Built-in user management with role-based permissions
- **API Authentication**: Secure API access with token-based authentication
- **Audit Logging**: Track all job executions and system changes

### What Makes CronAPI Different?

#### Compared to Celery:
- **API-First**: While Celery requires Python code for task definition, CronAPI allows job management via REST API
- **Language Independence**: Jobs can be defined and managed from any language, not just Python
- **Built-in UI Potential**: REST API design makes it easy to build custom UIs
- **Simpler Architecture**: No message broker required for basic operation
- **Job Dependencies**: Native support for job dependencies and chaining
- **Parameter Validation**: Built-in JSON Schema validation for job parameters

#### Compared to Traditional Cron:
- **Dynamic Updates**: No need to edit crontab files or restart services
- **API Control**: Full programmatic control over job scheduling
- **Rich Logging**: Detailed execution history and status tracking
- **Dependencies**: Support for complex job dependencies
- **Distribution**: Built-in support for distributed operation
- **Modern Interface**: REST API and potential for web UI

## Deployment Options

### Docker Deployment (Recommended)

1. **Single Instance**:
```bash
# Build and start the service
docker compose up -d cronapi

# Scale to multiple instances
docker compose up -d --scale cronapi=3
```

2. **Distributed Setup with Redis**:
```bash
# Start both CronAPI and Redis
docker compose up -d

# View logs
docker compose logs -f
```

3. **Configuration**:
The Docker setup includes:
- Multi-stage build for smaller image size
- Non-root user for security
- Volume mounts for persistent data
- Health checks for both services
- Automatic restart policies
- Redis for distributed locking

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/bm-197/cronapi.git
cd cronapi

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

1. Start the server:
```bash
python -m uvicorn main:app --reload
```

2. Create a new job via API:
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example-job",
    "expr": "*/5 * * * *",
    "code": "async def job_function():\n    print(\"Hello from CronAPI!\")",
    "tags": ["example"],
    "is_async": true
  }'
```

3. View job status:
```bash
curl http://localhost:8000/jobs/example-job
```

### Advanced Features

#### Job Dependencies
```json
{
  "name": "dependent-job",
  "expr": "0 * * * *",
  "dependencies": ["first-job", "second-job"],
  "on_success": ["notification-job"],
  "on_failure": ["error-handler-job"]
}
```

#### Parameter Schema
```json
{
  "name": "parameterized-job",
  "parameters_schema": {
    "type": "object",
    "properties": {
      "user_id": {"type": "string"},
      "action": {"enum": ["start", "stop", "restart"]}
    },
    "required": ["user_id", "action"]
  }
}
```

## Configuration

### Environment Variables
- `REDIS_URL`: Redis connection URL (optional, for distributed setup)
- `DATABASE_PATH`: SQLite database path (default: "cron_state.db")

### Security
- Default admin user is created on first run
- Use `/auth/token` endpoint to obtain access tokens
- All job management endpoints require authentication

## TODO List

### Short-term Improvements
- [ ] Add Prometheus metrics endpoint for monitoring
- [ ] Implement job timeout configuration
- [ ] Add support for job retry policies
- [ ] Create a web-based UI for job management
- [ ] Add support for job templates
- [ ] Implement job versioning

### Medium-term Goals
- [ ] Add support for more backend databases (PostgreSQL, MongoDB)
- [ ] Implement job execution queues with priorities
- [ ] Add support for job execution notifications (email, Slack, etc.)
- [ ] Create a plugin system for custom job runners
- [ ] Add support for job execution history cleanup policies

### Long-term Vision
- [ ] Implement a distributed file storage system for job artifacts
- [ ] Add support for workflow definitions (DAGs)
- [ ] Create a marketplace for sharing job templates
- [ ] Implement machine learning for job optimization
- [ ] Add support for geographic job distribution
- [ ] Create mobile apps for monitoring and management
