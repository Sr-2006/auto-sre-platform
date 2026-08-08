import os
import json
import time
import hashlib
import tempfile
from datetime import datetime

DUMP_DIR = "telemetry_dumps"
OUTPUT_DIR = "frontend_data"
MAX_RECORDS = 500

def get_latest_batch_dir():
    try:
        dirs = [os.path.join(DUMP_DIR, d) for d in os.listdir(DUMP_DIR) if d.startswith("batch_")]
        if not dirs:
            return None
        return max(dirs)
    except Exception:
        return None

def calculate_cpu_percent(stats):
    try:
        cpu_stats = stats.get('cpu_stats', {})
        precpu_stats = stats.get('precpu_stats', {})
        
        cpu_usage = cpu_stats.get('cpu_usage', {})
        precpu_usage = precpu_stats.get('cpu_usage', {})
        
        cpu_delta = cpu_usage.get('total_usage', 0) - precpu_usage.get('total_usage', 0)
        system_delta = cpu_stats.get('system_cpu_usage', 0) - precpu_stats.get('system_cpu_usage', 0)
        
        if system_delta > 0.0 and cpu_delta > 0.0:
            num_cpus = cpu_stats.get('online_cpus')
            if not num_cpus:
                percpu = cpu_usage.get('percpu_usage')
                num_cpus = len(percpu) if percpu else 1
            return (cpu_delta / system_delta) * num_cpus * 100.0
    except Exception:
        pass
    return 0.0

def calculate_memory_percent(stats):
    try:
        memory_stats = stats.get('memory_stats', {})
        usage = memory_stats.get('usage', 0)
        limit = memory_stats.get('limit', 0)
        if limit > 0:
            return (usage / limit) * 100.0
    except Exception:
        pass
    return 0.0

def atomic_write(filepath, data):
    dir_name = os.path.dirname(filepath)
    os.makedirs(dir_name, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=dir_name)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=4)
    try:
        os.replace(temp_path, filepath)
    except PermissionError:
        # Fallback to direct write if target is locked/unreplaceable
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        try:
            os.remove(temp_path)
        except Exception:
            pass

def read_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return []

def run_sync_loop():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    empty_schemas = {
        "causality.json": {"root_cause": "", "confidence": 0, "evidence": []},
        "cost_and_roi.json": {"estimated_cost": 0.0, "impact": "none"},
        "analytics.json": {"system_health_score": 100, "active_warnings": 0}
    }
    
    for filename, schema in empty_schemas.items():
        filepath = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(filepath):
            atomic_write(filepath, schema)

    while True:
        latest_batch = get_latest_batch_dir()
        if latest_batch:
            time_series_path = os.path.join(OUTPUT_DIR, "time_series.json")
            events_path = os.path.join(OUTPUT_DIR, "events_and_incidents.json")
            status_path = os.path.join(OUTPUT_DIR, "status.json")

            time_series_data = read_json(time_series_path)
            events_data = read_json(events_path)

            exited_or_unhealthy_count = 0
            network_state_file = os.path.join(latest_batch, "network_state.json")
            if os.path.exists(network_state_file):
                with open(network_state_file, 'r') as f:
                    status_data = json.load(f)
                atomic_write(status_path, status_data)
                
                core_services = ["api-gateway", "auth-service", "order-service", "payment-service", "postgres-db", "redis", "rabbitmq"]
                for item in status_data:
                    name = item.get("name")
                    if name in core_services:
                        status = item.get("status", "").lower()
                        health = item.get("health", "").lower()
                        if status == "exited" or status == "dead" or health == "unhealthy":
                            exited_or_unhealthy_count += 1

            high_resource_count = 0
            active_warnings = 0

            for filename in os.listdir(latest_batch):
                filepath = os.path.join(latest_batch, filename)
                
                if filename.endswith("_metrics.json"):
                    with open(filepath, 'r') as f:
                        stats = json.load(f)
                    
                    container_name = filename.replace("_metrics.json", "")
                    cpu_pct = calculate_cpu_percent(stats)
                    mem_pct = calculate_memory_percent(stats)
                    mem_usage = stats.get('memory_stats', {}).get('usage', 0)
                    
                    if cpu_pct > 85.0 or mem_pct > 90.0:
                        high_resource_count += 1
                    
                    metric_entry = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "container": container_name,
                        "cpu_percent": cpu_pct,
                        "memory_usage": mem_usage,
                        "memory_usage_percent": mem_pct
                    }
                    time_series_data.append(metric_entry)

                elif filename.endswith("_logs.txt"):
                    with open(filepath, 'r') as f:
                        log_content = f.read().strip()
                    
                    if log_content:
                        container_name = filename.replace("_logs.txt", "")
                        log_hash = hashlib.sha256(log_content.encode()).hexdigest()
                        
                        for line in log_content.splitlines():
                            upper_line = line.upper()
                            if "WARN" in upper_line or "ERROR" in upper_line or "FATAL" in upper_line:
                                active_warnings += 1
                        
                        event_entry = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "container": container_name,
                            "log_hash": log_hash,
                            "content": log_content
                        }
                        
                        if not any(e.get("log_hash") == log_hash for e in events_data):
                            events_data.append(event_entry)

            # Calculate health score starting at 100
            system_health_score = 100
            system_health_score -= (exited_or_unhealthy_count * 20)
            system_health_score -= (high_resource_count * 10)
            
            has_critical = False
            has_high = False
            processed_incidents_path = os.path.join(OUTPUT_DIR, "processed_incidents.json")
            if os.path.exists(processed_incidents_path):
                with open(processed_incidents_path, 'r') as f:
                    try:
                        processed_incidents = json.load(f)
                        incidents_list = []
                        if isinstance(processed_incidents, dict):
                            incidents_list = processed_incidents.get("incidents", [])
                        elif isinstance(processed_incidents, list):
                            incidents_list = processed_incidents
                        
                        for incident in incidents_list:
                            severity = incident.get("severity", "").upper()
                            if severity == "CRITICAL":
                                has_critical = True
                            elif severity == "HIGH":
                                has_high = True
                    except Exception:
                        pass
            
            if has_critical:
                system_health_score -= 30
            elif has_high:
                system_health_score -= 15
                
            system_health_score = max(0, min(100, system_health_score))
            
            analytics_path = os.path.join(OUTPUT_DIR, "analytics.json")
            analytics_data = {
                "system_health_score": system_health_score,
                "active_warnings": active_warnings
            }
            atomic_write(analytics_path, analytics_data)

            time_series_data = time_series_data[-MAX_RECORDS:]
            events_data = events_data[-MAX_RECORDS:]

            atomic_write(time_series_path, time_series_data)
            atomic_write(events_path, events_data)

        time.sleep(5)

if __name__ == "__main__":
    run_sync_loop()