import unittest
from unittest.mock import patch

from copilot.tools import job_scheduler


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "http://test")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.posts = []
        self.deletes = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append((url, json, headers))
        if url.endswith("/jobs"):
            return _FakeResponse(200, {"id": "job-123", "name": "demo"})
        if url.endswith("/jobs/job-123/run"):
            return _FakeResponse(200, {"ok": False, "error": "boom"})
        raise AssertionError(f"Unexpected POST url: {url}")

    async def delete(self, url, headers=None):
        self.deletes.append((url, headers))
        if url.endswith("/jobs/job-123"):
            return _FakeResponse(200, {"ok": True})
        raise AssertionError(f"Unexpected DELETE url: {url}")


class JobSchedulerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_create_analysis_job_deletes_failed_job_after_validation(self):
        with patch("copilot.tools.job_scheduler.httpx.AsyncClient", _FakeAsyncClient):
            result = await job_scheduler.create_analysis_job.ainvoke(
                {
                    "name": "demo job",
                    "analysis_code": "print('hello')",
                    "config": {"configurable": {"thread_id": "thread-1"}},
                }
            )

        self.assertIn("error", result)
        self.assertTrue(result["deleted_failed_job"])
        self.assertEqual(result["job"]["id"], "job-123")
        self.assertEqual(result["test_run"]["error"], "boom")


if __name__ == "__main__":
    unittest.main()
