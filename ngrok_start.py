import os
import sys
import time
import subprocess
from pyngrok import ngrok
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    print("[INFO] Starting CyberLens System & Creating Public Demo Tunnel...")
    
    # 1. Start both servers in the background via run.py
    run_cmd = [sys.executable, "run.py"]
    print("[INFO] Executing run.py to launch backend server...")
    server_process = subprocess.Popen(
        run_cmd,
        cwd=os.getcwd()
    )
    
    # Wait for the servers to startup
    print("[INFO] Waiting 6 seconds for server to initialize...")
    time.sleep(6)
    
    # 2. Start ngrok tunnel on port 8000
    print("[INFO] Connecting ngrok tunnel to FastAPI on port 8000...")
    try:
        # Set auth token from environment
        auth_token = os.getenv("NGROK_AUTH_TOKEN")
        if auth_token:
            ngrok.set_auth_token(auth_token.strip())
        else:
            print("[WARN] Warning: NGROK_AUTH_TOKEN not found in .env. Attempting tunnel without authtoken...")
 
        # Open tunnel
        public_url = ngrok.connect(8000, proto="http")
        
        print("\n" + "="*70)
        print("[SUCCESS] PUBLIC DEMO TUNNEL CREATED SUCCESSFULLY!")
        print(f"SHARE THIS LINK: {public_url}")
        print("="*70 + "\n")
        
        # Keep running until Ctrl+C or servers stop
        try:
            while True:
                if server_process.poll() is not None:
                    print("❌ Server stopped. Exiting.")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 KeyboardInterrupt received. Closing ngrok tunnel and server...")
            
    except Exception as e:
        print(f"\n❌ Error starting ngrok tunnel: {e}")
        print("💡 Ensure you have installed pyngrok and your authtoken is configured if required.")
        print("💡 You can configure it via terminal: ngrok config add-authtoken <YOUR_TOKEN>\n")
        
    finally:
        # Clean shutdown
        print("Shutting down server...")
        server_process.terminate()
        server_process.wait()
        
        print("Killing ngrok tunnels...")
        ngrok.kill()
        print("👋 All services stopped.")

if __name__ == "__main__":
    main()
