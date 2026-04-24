import uvicorn
from . import config

if __name__ == "__main__":
    uvicorn.run(
        "email_service.app:app",
        host=config.SERVICE_HOST,
        port=config.SERVICE_PORT,
        reload=False,
    )
