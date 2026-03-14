"""Entry point for `python -m deliberation`."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "deliberation.main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )
