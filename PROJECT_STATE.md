# Auto-SRE Platform: Project State & Architecture Registry

## Metadata & Status Stamp

| Attribute | Details |
| :--- | :--- |
| **Project Name** | Smart Horizon Hackathon - V2 Microservices & Auto-SRE Engine |
| **Last Modified Date** | August 8, 2026 |
| **Current Phase** | Phase 1 & Telemetry Layer Complete. ML Training Dataset Compiled & Packaged. |
| **Repository State** | Fully instrumented, dockerized, telemetry extraction robustly handling Windows OS file locks. |

---

## 1. System Architecture & Tech Stack

The system is a distributed, event-driven microservices architecture built for high throughput, scalability, and robust observability.

*   **API Gateway (Java / Spring Boot 3.2.5):** Entry point routing traffic internally. Contains a `FailureInjectionFilter` that simulates thread blocks, rate-limiting, and connection resets.
*   **Auth Service (Java / Spring Boot 3.2.5):** Coordinates user registration and JWT generation. Interacts with Postgres for storage and Redis for caching.
*   **Order Service (Java / Spring Boot 3.2.3):** Core order creation and query routing. Communicates with RabbitMQ for event-driven coordination and Postgres for transactional records.
*   **Payment Service (Java / Spring Boot 3.2.3):** Handles simulated financial transactions and coordinates event updates via RabbitMQ.
*   **Infrastructure Layer:**
    *   **PostgreSQL 16 (Alpine):** Consolidates isolated schemas (`auth_db`, `order_db`, `payment_db`).
    *   **Redis 7 (Alpine):** Distributed key-value cache.
    *   **RabbitMQ 3 (Management/Alpine):** Event message broker.
*   **Observability Pipeline:**
    *   **OpenTelemetry Collector:** Aggregates span data from services using the OTLP/gRPC protocol on port `4317`.
    *   **Jaeger:** Serves as the distributed tracing storage and query UI (`http://localhost:16686`).
    *   **Prometheus:** Pulls metric data from the microservices `/actuator/prometheus` endpoints.
    *   **Grafana:** Dashboard analytics interface on port `3000`.

---

## 2. File & Script Specification Registry

### A. Simulators & Traffic Generators
*   **`load_generator.py`:** A Python traffic pump that runs continuously, invoking internal routes on the gateway (`http://localhost:8080`). It specifically triggers failure-injection paths (e.g. `/chaos/timeout`, `/chaos/oom`, `/chaos/latency`) to populate error logs.
*   **`chaos_orchestrator.py`:** An infrastructure-level fault injection engine. It connects to the host's Docker daemon, randomly pauses a key dependency (`postgres-db` or `redis`) for 30 seconds, and then restores it, forcing the microservices to handle network cut-offs.

### B. Telemetry Daemons
*   **`continuous_telemetry.py`:** Polls the Docker engine every 5 seconds to query container lifecycle states and fetch resource metrics (CPU/Memory usage). It pulls stdout/stderr logs from the containers and dumps batch directories into `telemetry_dumps/`.
*   **`frontend_data_sync.py`:** Formats raw dumps into clean JSON schemas in `frontend_data/`. It is optimized for Windows OS by resolving absolute paths and using a retry/fallback mechanism on `atomic_write` to handle file-locking. It dynamically computes:
    *   `memory_usage_percent` (relative to the container limits).
    *   `cpu_percent` (accounting for multiple WSL2 logical cores).
    *   `system_health_score` (100 baseline, degraded by container outages, high resource usage, and error severity).
    *   `active_warnings` (log scanner counting `WARN` and `ERROR` keywords).

### C. SRE Log Processors & Packagers
*   **`phase1_processor.py`:** The frontline log engine. It reads recent events, parses them using Drain3, assigns severity keywords, and calculates a priority score.
*   **`package_ml_dataset.py`:** An orchestrator script that compiles all distinct telemetry files (`status.json`, `time_series.json`, `events_and_incidents.json`, `processed_incidents.json`) into a single joined model: `ml_dataset/unified_master_dataset.json`.

---

## 3. Log Parsing & Unsupervised Clustering (Drain3)

To group millions of unstructured logs into distinct, manageable failure modes without manual labelling, the SRE engine implements the **Drain3** algorithm:

*   **Tree-Structured Parsing:** Drain3 builds a parse tree based on log structure. It uses tokens and length-based nodes to group similar messages together.
*   **Dynamic Parameter Masking:** Regular expressions replace variable details in logs (such as IPs, Hex addresses, UUIDs, and numbers) with standard tokens (e.g., `<IP>`, `<HEX>`, `<UUID>`, `<NUM>`).
*   **Composite Isolation Key:** The engine constructs a composite namespace identifier:
    $$\text{Composite ID} = \text{container\_name} + \text{"\_"} + \text{drain\_cluster\_id}$$
    This guarantees that identical log templates (e.g., connection exceptions) are isolated and blamed on the specific microservice container that threw them.

---

## 4. Priority Scoring Logic

Incidents are prioritized in the queue sequentially based on a composite priority score:

$$\text{Priority Score} = (\text{Base Severity Weight} \times \log_{10}(\text{Occurrence Count} + 1)) + \text{State Penalty}$$

### Parameters:
1.  **Base Severity Weight:** Determined by scanning the log header:
    *   `CRITICAL` (40): Catastrophic system errors (`OOM`, `FATAL`, `TIMEOUT`, `CONNECTION RESET`).
    *   `HIGH` (30): Application errors (`ERROR`, `EXCEPTION`, `FAILED`).
    *   `MEDIUM` (20): System warnings (`WARN`).
2.  **Logarithmic Velocity Scaling:** $\log_{10}(\text{Occurrence Count} + 1)$ prevents high-frequency warnings from flooding out low-frequency, highly critical crashes. It scales log volumes down logarithmically (e.g. 1 occurrence $\approx 0.30$; 1,000 occurrences $\approx 3.00$).
3.  **State Penalty:** Adds a flat **+50 point penalty** if the container's Docker state is `exited`, `paused`, or `unhealthy`, forcing dead nodes to the top of the queue.

---

## 5. Failure Simulation Catalog

The SRE engine currently logs and categorizes the following simulated failure signatures:

| Service / Container | Injected Fault | Resulting Log Signatures | Mined Template Example |
| :--- | :--- | :--- | :--- |
| **`postgres-db`** (Paused) | Dependency Outage | Connection validation failure, Spring Actuator health timeouts. | `<NUM> com.zaxxer.hikari.pool.PoolBase : HikariPool-<NUM> - Failed to validate connection org.postgresql.jdbc.PgConnection (This connection has been closed.)` |
| **`redis`** (Paused) | Cache Timeout | Spring Boot health indicator thread blocks. | `o.s.b.a.health.HealthEndpointSupport : Health contributor (redis) took <NUM>ms to respond` |
| **`api-gateway`** | Exporter congestion | Trace export failures in background threads. | `i.o.exporter.internal.http.HttpExporter : Failed to export spans. Full error message: Connection reset` |
| **`payment-service`** | Simulated DB lock | Database pool initialization failures. | `com.zaxxer.hikari.pool.HikariPool : HikariPool-<NUM> - Exception during pool initialization.` |
| **`order-service`** | Simulated metrics lag | Prometheus metrics scraper handler failures. | `GlobalExceptionHandler : [SRE-LOG-EVENT] System Failure: /actuator/prometheus. StackTrace:` |

---

## 6. ML Dataset Schema (`unified_master_dataset.json`)

The output of the dataset compiler binds all angles of telemetry into a clean record schema for ML models:

```json
[
  {
    "incident_id": "api-gateway_2",
    "target_service": "api-gateway",
    "incident_priority_score": 79.65,
    "incident_severity": "CRITICAL",
    "log_pattern_template": "<NUM>-<NUM>-<NUM>T... i.o.exporter.internal.http.HttpExporter : Failed to export spans. Connection reset",
    "occurrence_count": 97,
    "service_health_at_capture": {
      "docker_status": "running",
      "health_check": "healthy"
    },
    "topology_context": {
      "service_role": "edge-routing-and-rate-limiting",
      "depends_on_services": ["auth-service", "order-service", "payment-service", "otel-collector"],
      "exposed_ports": ["8080:8080"]
    },
    "associated_logs_samples": [
      {
        "timestamp": "2026-08-08T12:55:44.678Z",
        "log_content": "...java.net.SocketException: Connection reset...",
        "trace_id": null,
        "span_id": null
      }
    ],
    "service_performance_samples": [
      {
        "timestamp": "2026-08-08T13:42:03.177Z",
        "cpu_percent": 12.37,
        "memory_usage": 313708544,
        "memory_usage_percent": 3.76
      }
    ]
  }
]
```
This comprehensive structured dataset allows models to jointly analyze logs, metrics, topologies, and trace contexts.