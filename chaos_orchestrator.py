import docker
import time

client = docker.from_env()

def inject_chaos():
    print("[CHAOS] Initializing ARA Chaos Orchestrator (Silent Infra Pump)...")
    
    cycle = ["postgres-db", "redis"]
    
    while True:
        for target in cycle:
            try:
                container = client.containers.get(target)
                container.reload()
                
                if container.status == 'paused':
                    print(f"[INFRA] {target} is already paused, unpausing first...")
                    container.unpause()
                    time.sleep(2)

                print(f"[INFRA] Pausing {target}")
                container.pause()
                
                time.sleep(10)
                
                print(f"[INFRA] Restoring {target}")
                container.reload()
                if container.status == 'paused':
                    container.unpause()
                
                time.sleep(10)
                
            except docker.errors.NotFound:
                print(f"[ERROR] Could not find '{target}'. Is the container running?")
                time.sleep(10)
            except Exception as e:
                print(f"[ERROR] Chaos injection failed on {target}: {e}")
                try:
                    container.unpause()
                except:
                    pass
                time.sleep(10)

if __name__ == "__main__":
    inject_chaos()