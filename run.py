import os
import sys
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Forge IDE on http://{host}:{port}")
    uvicorn.run("backend.server:app", host=host, port=port, reload=False)
