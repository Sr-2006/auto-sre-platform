import time
import requests

def generate_traffic():
    headers = {"X-Chaos-Trigger": "true"}
    
    triggers = [
        {"name": "Order_Timeout", "url": "http://localhost:8080/api/v1/orders/chaos/timeout"},
        {"name": "Payment_OOM", "url": "http://localhost:8080/api/v1/payments/chaos/oom"},
        {"name": "Auth_Corruption", "url": "http://localhost:8080/api/v1/auth/chaos/corruption"},
        {"name": "Payment_Latency", "url": "http://localhost:8080/api/v1/payments/chaos/latency"}
    ]
    
    while True:
        for trigger in triggers:
            try:
                print(f"[TRIGGERED] {trigger['name']}")
                # We use a short timeout so the script doesn't hang forever, but long enough for latency to hit
                requests.get(trigger["url"], headers=headers, timeout=10)
            except requests.exceptions.RequestException as e:
                # We expect these requests to fail/timeout, which is the point of the chaos generator
                pass
            
            # Wait a bit before the next trigger to allow the system to process the logs
            time.sleep(5)

if __name__ == "__main__":
    print("Starting Auto-SRE Traffic & Chaos Generator (Silent Data Pump)...")
    generate_traffic()
