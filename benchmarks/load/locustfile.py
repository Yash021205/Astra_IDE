"""
Load test (tech-stack §9: "pytest + locust"). Exercises the hot API paths a
real session hits: each simulated user registers once, then loops creating
workspaces, listing them, running code, and reading carbon intensity.

    pip install locust
    locust -f benchmarks/load/locustfile.py --host http://localhost:8000
    # headless, 50 users, 5/s ramp, 2 min:
    locust -f benchmarks/load/locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 5 -t 2m

Watch the effect live on the Grafana "ASTRA-IDE — Platform Overview" dashboard
(HTTP rate/latency, workspace creations, pending-queue → KEDA scale-up).
"""
import time
import uuid

from locust import HttpUser, between, task


class WorkspaceUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Register a fresh user and keep the JWT for subsequent calls."""
        u = f"load_{uuid.uuid4().hex[:10]}"
        r = self.client.post("/api/v1/auth/register", json={
            "email": f"{u}@load.test", "username": u, "password": "password123",
        }, name="/auth/register")
        self.token = r.json().get("access_token", "") if r.ok else ""
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def create_workspace(self):
        self.client.post("/api/v1/workspaces", json={
            "name": f"ws-{int(time.time())}", "language": "python",
        }, headers=self.headers, name="/workspaces [POST]")

    @task(5)
    def list_workspaces(self):
        self.client.get("/api/v1/workspaces", headers=self.headers,
                        name="/workspaces [GET]")

    @task(2)
    def run_code(self):
        # find a workspace, then execute trivial code in it
        r = self.client.get("/api/v1/workspaces", headers=self.headers,
                            name="/workspaces [GET]")
        items = r.json().get("items", []) if r.ok else []
        if not items:
            return
        wid = items[0]["id"]
        self.client.post(f"/api/v1/workspaces/{wid}/execute", json={
            "language": "python", "code": "print(sum(range(1000)))",
        }, headers=self.headers, name="/workspaces/:id/execute")

    @task(1)
    def carbon(self):
        self.client.get("/api/v1/carbon/intensity?zone=DK-DK1",
                        headers=self.headers, name="/carbon/intensity")
