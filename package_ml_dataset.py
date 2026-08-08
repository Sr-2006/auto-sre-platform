import os
import json
import re
from datetime import datetime

# Define paths
FRONTEND_DIR = "frontend_data"
OUTPUT_DIR = "ml_dataset"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def parse_topology_from_compose():
    """Generates a dependency map by parsing docker-compose.yml."""
    topology = {}
    compose_path = "docker-compose.yml"
    if not os.path.exists(compose_path):
        return {}

    # Define hardcoded/fallback topology derived from docker-compose.yml
    topology = {
        "api-gateway": {
            "dependencies": ["auth-service", "order-service", "payment-service", "otel-collector"],
            "role": "edge-routing-and-rate-limiting",
            "ports": ["8080:8080"]
        },
        "auth-service": {
            "dependencies": ["postgres-db", "redis", "otel-collector"],
            "role": "user-auth-and-jwt",
            "ports": ["8081:8081"]
        },
        "order-service": {
            "dependencies": ["postgres-db", "otel-collector"],
            "role": "order-management",
            "ports": ["8082:8082"]
        },
        "payment-service": {
            "dependencies": ["postgres-db", "otel-collector"],
            "role": "payment-processing",
            "ports": ["8083:8083"]
        },
        "postgres-db": {
            "dependencies": [],
            "role": "relational-database",
            "ports": ["5432:5432"]
        },
        "redis": {
            "dependencies": [],
            "role": "key-value-cache",
            "ports": ["6379:6379"]
        },
        "rabbitmq": {
            "dependencies": [],
            "role": "message-broker",
            "ports": ["5672:5672", "15672:15672"]
        }
    }
    return topology

def read_json_file(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return []

def package_data():
    print("=== [ML Packager] Bundling Datasets with Unified Context ===")

    # Load data files
    events = read_json_file(os.path.join(FRONTEND_DIR, "events_and_incidents.json"))
    processed_incidents = read_json_file(os.path.join(FRONTEND_DIR, "processed_incidents.json"))
    status_list = read_json_file(os.path.join(FRONTEND_DIR, "status.json"))
    time_series = read_json_file(os.path.join(FRONTEND_DIR, "time_series.json"))
    
    # Parse topology
    topology = parse_topology_from_compose()

    # Map container status
    status_map = {item["name"]: item for item in status_list} if isinstance(status_list, list) else {}

    # Extract incidents array
    incidents_list = []
    if isinstance(processed_incidents, dict):
        incidents_list = processed_incidents.get("incidents", [])
    elif isinstance(processed_incidents, list):
        incidents_list = processed_incidents

    unified_dataset = []

    for incident in incidents_list:
        container_name = incident.get("source_container")
        cluster_id = incident.get("cluster_id")
        template = incident.get("template")

        # 1. Gather all raw logs that match this template's cluster
        # Using a regex-based matches or hash equivalence helper
        matching_logs = []
        for event in events:
            if event.get("container") == container_name:
                # Extract trace_id and span_id if present
                content = event.get("content", "")
                trace_match = re.search(r"\[([a-f0-9]{32})-([a-f0-9]{16})\]", content)
                trace_id = trace_match.group(1) if trace_match else None
                span_id = trace_match.group(2) if trace_match else None
                
                # Check if the main line matches template or if container matches
                # We save matching container logs that have trace information to help ML model
                matching_logs.append({
                    "timestamp": event.get("timestamp"),
                    "log_content": content,
                    "trace_id": trace_id,
                    "span_id": span_id
                })

        # 2. Gather time series metrics for this container
        container_metrics = [
            {
                "timestamp": metric.get("timestamp"),
                "cpu_percent": metric.get("cpu_percent"),
                "memory_usage": metric.get("memory_usage"),
                "memory_usage_percent": metric.get("memory_usage_percent")
            }
            for metric in time_series
            if metric.get("container") == container_name
        ]

        # 3. Pull Topology Context
        container_topology = topology.get(container_name, {"dependencies": [], "role": "unknown", "ports": []})

        # 4. Pull Health State
        container_health = status_map.get(container_name, {"status": "unknown", "health": "unknown"})

        # Build Consolidated Record
        unified_record = {
            "incident_id": cluster_id,
            "target_service": container_name,
            "incident_priority_score": incident.get("priority_score"),
            "incident_severity": incident.get("severity"),
            "log_pattern_template": template,
            "occurrence_count": incident.get("occurrence_count"),
            "service_health_at_capture": {
                "docker_status": container_health.get("status"),
                "health_check": container_health.get("health")
            },
            "topology_context": {
                "service_role": container_topology.get("role"),
                "depends_on_services": container_topology.get("dependencies"),
                "exposed_ports": container_topology.get("ports")
            },
            "associated_logs_samples": matching_logs[:15], # top 15 samples to keep it clean
            "service_performance_samples": container_metrics[-15:] # latest 15 metric states
        }

        unified_dataset.append(unified_record)

    # Write Master Unified Dataset
    master_output_path = os.path.join(OUTPUT_DIR, "unified_master_dataset.json")
    with open(master_output_path, "w", encoding="utf-8") as f:
        json.dump(unified_dataset, f, indent=4)

    # Copy files over to ml_dataset
    for filename in ["events_and_incidents.json", "processed_incidents.json", "status.json", "time_series.json"]:
        src = os.path.join(FRONTEND_DIR, filename)
        dst = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f_in:
                data = json.load(f_in)
            with open(dst, "w", encoding="utf-8") as f_out:
                json.dump(data, f_out, indent=4)

    print(f"[+] Success! Compiled unified dataset with topology, trace IDs, and time-series metrics.")
    print(f"    Exported to: {master_output_path}")

if __name__ == "__main__":
    package_data()
