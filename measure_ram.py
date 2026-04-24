
import psutil
import subprocess
import time
import sys
import os

def cleanup():
    print("Cleaning up old processes...")
    for p in psutil.process_iter(['name']):
        try:
            if "python" in p.info['name'].lower():
                cmd = " ".join(p.cmdline())
                if "main.py" in cmd or "aura_launcher.py" in cmd:
                    print(f"Killing {p.pid}")
                    p.kill()
        except:
            pass
    # Give OS time to release shared memory
    time.sleep(2)

def measure_aura_ram():
    cleanup()
    
    print("Starting AURA Engine (main.py)...")
    # Set encoding for subprocess
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    core_proc = subprocess.Popen([sys.executable, "main.py"], env=env)
    
    # Wait for full initialization
    print("Waiting 15 seconds for MediaPipe and Camera to warm up...")
    time.sleep(15)
    
    total_rss = 0
    try:
        parent = psutil.Process(core_proc.pid)
        procs = [parent] + parent.children(recursive=True)
        
        print("\nProcess Breakdown:")
        for p in procs:
            try:
                name = p.name()
                if name == "python.exe":
                    # Try to get the script name
                    try: cmd = " ".join(p.cmdline()); name = cmd.split()[-1]
                    except: pass
                rss = p.memory_info().rss / (1024 * 1024)
                total_rss += rss
                print(f"  - {name} (PID {p.pid}): {rss:.2f} MB")
            except:
                pass
                
        # Also include launcher cost (usually ~40-60MB)
        print(f"\nEngine Total: {total_rss:.2f} MB")
        print(f"Estimated Launcher Cost: ~50.00 MB")
        print(f"Total System Cost: ~{total_rss + 50:.2f} MB")
        
    finally:
        # Cleanup
        try:
            parent = psutil.Process(core_proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except:
            pass

if __name__ == "__main__":
    measure_aura_ram()
