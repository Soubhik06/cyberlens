import os
import sys
import time
import subprocess
import psutil

def terminate_pid(pid, port):
    try:
        proc = psutil.Process(pid)
        print(f"[INFO] Port {port} in use by process: {proc.name()} (PID: {pid}). Terminating...")
        proc.terminate()
        try:
            proc.wait(timeout=3)
            print(f"[INFO] Process {pid} terminated.")
        except psutil.TimeoutExpired:
            proc.kill()
            print(f"[INFO] Process {pid} force-killed.")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

def kill_process_on_ports(ports):
    # Try net_connections first
    try:
        conns = psutil.net_connections(kind='inet')
        for conn in conns:
            if conn.laddr.port in ports and conn.pid:
                terminate_pid(conn.pid, conn.laddr.port)
    except (psutil.AccessDenied, AttributeError):
        # Fall back to iterating over processes individually if net_connections requires administrative privileges
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections(kind='inet'):
                    if conn.laddr.port in ports:
                        terminate_pid(proc.info['pid'], conn.laddr.port)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except:
        pass
        
    print("[INFO] Starting CyberLens System...")
    
    # Clean up target ports before startup
    kill_process_on_ports([8000, 8501])
    
    print("[INFO] Launching FastAPI backend on http://localhost:8000 ...")
    
    backend_cmd = [
        sys.executable, "-m", "uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"
    ]
    backend_process = subprocess.Popen(
        backend_cmd,
        cwd=os.getcwd()
    )
    
    print("\n[SUCCESS] Server launched successfully. Press Ctrl+C to stop the server.")
    
    try:
        while True:
            # Check status of process
            if backend_process.poll() is not None:
                print(f"[ERROR] Backend exited unexpectedly with code {backend_process.poll()}.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] KeyboardInterrupt received. Shutting down server...")
    finally:
        print("Terminating Backend process...")
        backend_process.terminate()
        backend_process.wait()
        print("[INFO] Server stopped. Goodbye!")

if __name__ == "__main__":
    main()
