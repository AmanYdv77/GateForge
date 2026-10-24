import random

from locust import HttpUser, between, task


class GatewayLoadTestUser(HttpUser):
    """High-throughput load testing user simulating real-world API gateway client traffic."""

    wait_time = between(0.001, 0.005)

    # Pre-configured test key prefixes matching seeded fixtures
    TEST_API_KEYS = [
        "gfg_live_benchkey000100000000000000000000",
        "gfg_live_benchkey000200000000000000000000",
        "gfg_live_benchkey000300000000000000000000",
    ]

    def on_start(self) -> None:
        """Assign random API key to virtual user."""
        self.api_key = random.choice(self.TEST_API_KEYS)

    @task(10)
    def test_gateway_verification(self) -> None:
        """Simulate high-frequency edge authentication and rate limit verification."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Forwarded-For": "192.168.1.100",
        }
        with self.client.get(
            "/api/v1/gateway/verify",
            headers=headers,
            catch_response=True,
            name="/api/v1/gateway/verify",
        ) as response:
            # Under load, both 200 (allowed) and 429 (rate limited) are expected valid outcomes
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)
    def test_health_endpoint(self) -> None:
        """Lightweight health probe simulating load balancer heartbeat."""
        self.client.get("/health/live", name="/health/live")

    @task(1)
    def test_metrics_scrape(self) -> None:
        """Prometheus metrics scraper polling exposition endpoint."""
        self.client.get("/metrics", name="/metrics")
