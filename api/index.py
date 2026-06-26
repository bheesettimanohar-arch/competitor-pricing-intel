import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.cli.fast_api import get_fast_api_app

# Initialize the FastAPI app pointing to the 'app' directory
app = get_fast_api_app(
    agents_dir="app",
    web=True,
)
