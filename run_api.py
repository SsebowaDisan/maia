import os
import warnings

# Must be set BEFORE any other imports so filters apply to all transitive deps.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
warnings.filterwarnings("ignore", message=r"Field .* has conflict with protected namespace", category=UserWarning)
warnings.filterwarnings("ignore", message=r"urllib3.*chardet.*doesn't match")
warnings.filterwarnings("ignore", module=r"requests")
warnings.filterwarnings("ignore", message=r"ARC4 has been moved", category=DeprecationWarning)

from api.main import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
