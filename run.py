import os
import sys
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Agent Zero IDE on http://{host}:{port}")
    uvicorn.run("backend.server:app", host=host, port=port, reload=False)
