import logging
import toml
import threading
import subprocess
import datetime
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path
import sys

config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
wildwings_config = config["wildwings"]

# Setup logging with live output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(wildwings_config["logfile_path"], mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("wildwings")

# Global mission state
mission_thread = None
stop_mission_flag = threading.Event()
current_process = None
is_running = False
logs = []

def run_mission_background():
    """Execute mission in background thread"""
    global stop_mission_flag, current_process, is_running, logs
    try:
        if stop_mission_flag.is_set():
            logger.info("Mission stopped before execution")
            return

        logger.info("Starting WildWings mission")

        # Create mission directory
        mission_dir = Path("/app/mission")
        mission_dir.mkdir(exist_ok=True)

        # Execute launch.sh script
        script_path = Path("/app/launch.sh")
        if not script_path.exists():
            raise FileNotFoundError(f"Launch script not found: {script_path}")

        # Make script executable
        os.chmod(script_path, 0o755)

        # Run the launch script
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        current_process = subprocess.Popen(
            ["bash", str(script_path)],
            cwd="/app",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            env=env
        )

        is_running = True
        logger.info("Mission subprocess started successfully")

        # Stream output in real-time
        for line in iter(current_process.stdout.readline, ''):
            if stop_mission_flag.is_set():
                logger.info("Stop signal received, terminating mission")
                current_process.terminate()
                break

            if line.strip():
                log_entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {line.strip()}"
                logs.append(log_entry)
                logger.info(f"Mission output: {line.strip()}")

                # Keep only last 1000 log entries
                if len(logs) > 1000:
                    logs = logs[-1000:]

        current_process.wait()
        logger.info(f"Mission completed with return code: {current_process.returncode}")

    except Exception as e:
        logger.error(f"Mission failed: {str(e)}")
    finally:
        is_running = False
        current_process = None
        stop_mission_flag.clear()
        logger.info("Mission thread finished")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WildWings service starting up")
    yield
    logger.info("WildWings service shutting down")
    global mission_thread, stop_mission_flag, current_process, is_running
    if mission_thread and mission_thread.is_alive():
        logger.info("Stopping running mission during shutdown")
        stop_mission_flag.set()
        if current_process:
            current_process.terminate()
        mission_thread.join(timeout=5.0)
        is_running = False

app = FastAPI(
    title="WildWings Service",
    description="WildWings wildlife monitoring service",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[wildwings_config["cors_origin"]],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "WildWings Service", "status": "running"}

@app.post("/start_mission")
async def start_mission():
    logger.info("Start mission endpoint accessed")

    global mission_thread, stop_mission_flag, is_running

    if mission_thread and mission_thread.is_alive():
        logger.error("Mission already running")
        raise HTTPException(status_code=400, detail="Mission already running")

    try:
        # Clear any previous stop flag and start new mission
        stop_mission_flag.clear()
        mission_thread = threading.Thread(
            target=run_mission_background,
            name="WildWings-Mission"
        )
        mission_thread.start()

        logger.info("WildWings mission started successfully")
        return {
            "status": "success",
            "message": "WildWings mission started"
        }

    except Exception as e:
        logger.error(f"Failed to start mission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start mission: {str(e)}")
    

@app.post("/stop_mission")
async def stop_mission():
    logger.info("Stop mission endpoint accessed")

    global mission_thread, stop_mission_flag, current_process, is_running

    if not mission_thread or not mission_thread.is_alive():
        logger.info("No mission currently running")
        return {
            "status": "success",
            "message": "No mission currently running",
            "was_running": False
        }

    try:
        # Set stop flag
        stop_mission_flag.set()
        logger.info("Stop mission flag set")

        # Terminate the process if it exists
        if current_process:
            logger.info("Terminating current process")
            current_process.terminate()

            # Wait a bit for graceful termination
            try:
                current_process.wait(timeout=5)
                logger.info("Process terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate gracefully, forcing kill")
                current_process.kill()
                current_process.wait()

        # Wait for mission thread to finish
        if mission_thread and mission_thread.is_alive():
            logger.info("Waiting for mission thread to finish")
            mission_thread.join(timeout=10)
            if mission_thread.is_alive():
                logger.warning("Mission thread didn't finish within timeout")

        # Update state
        is_running = False

        logger.info("Mission stopped successfully")
        return {
            "status": "success",
            "message": "Mission stopped successfully",
            "was_running": True
        }

    except Exception as e:
        logger.error(f"Failed to stop mission: {str(e)}")
        # Still try to clean up state even if stopping failed
        is_running = False
        stop_mission_flag.set()
        return {
            "status": "error",
            "message": f"Error stopping mission: {str(e)}",
            "was_running": True
        }

@app.get("/mission_status")
async def mission_status():
    global mission_thread, stop_mission_flag, is_running, logs

    if mission_thread and mission_thread.is_alive():
        status = "running"
        if stop_mission_flag.is_set():
            status = "stopping"
    else:
        status = "idle"

    recent_logs = logs[-10:] if len(logs) > 10 else logs

    return {
        "status": status,
        "thread_alive": mission_thread.is_alive() if mission_thread else False,
        "stop_requested": stop_mission_flag.is_set(),
        "is_running": is_running,
        "total_logs": len(logs),
        "recent_logs": recent_logs
    }

@app.get("/logs")
async def get_logs(lines: int = 100):
    logger.info(f"Logs endpoint accessed - requesting {lines} lines")

    try:
        # Read from the log file configured in config.toml
        log_file_path = wildwings_config["logfile_path"]
        logger.info(f"Reading logs from: {log_file_path}")

        if not Path(log_file_path).exists():
            logger.warning(f"Log file not found at: {log_file_path}")
            return {"logs": ["Log file not found"], "total_lines": 0, "runtime_logs": logs[-lines:]}

        with open(log_file_path, 'r') as f:
            all_lines = f.readlines()

        # Get the last 'lines' number of lines
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        # Clean up the lines and return as list
        file_logs = [line.strip() for line in recent_lines if line.strip()]
        runtime_logs = logs[-lines:] if len(logs) > lines else logs

        logger.info(f"Returning {len(file_logs)} file log lines and {len(runtime_logs)} runtime log lines")
        return {
            "logs": file_logs,
            "total_lines": len(all_lines),
            "runtime_logs": runtime_logs,
            "total_runtime_logs": len(logs)
        }

    except Exception as e:
        logger.error(f"Failed to read logs: {str(e)}")
        return {
            "logs": [f"Error reading logs: {str(e)}"],
            "total_lines": 0,
            "runtime_logs": logs[-lines:] if logs else []
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=wildwings_config["host"],
        port=wildwings_config["port"],
        reload=wildwings_config["debug"],
        access_log=True
    )