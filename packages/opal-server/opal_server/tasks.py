from fastapi import APIRouter, Path


def setup_tasks_api():
    router = APIRouter()

    @router.get("/tasks/{task_id}")
    async def get_task_status(task_id: str = Path(..., title="Task ID")):
        try:
            from opal_server import worker
            from celery.result import AsyncResult
        except ImportError:
            return {"status": "async task support is disabled"}

        result: AsyncResult = worker.app.AsyncResult(task_id)

        return {
            "status": result.status
        }

    return router
