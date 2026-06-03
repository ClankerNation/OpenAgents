import requests
from ipaddress import ip_address, AddressValueError
from urllib.parse import urlparse
from datetime import datetime
import os

# Documentation block with agent metadata
agent_name = "api/routes/agents.py"
iso_timestamp = datetime.now().isoformat()
startup_instructions = """
1. Ensure Python is installed.
2. Install required packages: `pip install requests`.
3. Run the script using: `python api/routes/agents.py`.
"""
runtime_environment = {
    "os": os.name,
    "arch": os.uname().machine,
    "home_dir": os.path.expanduser("~"),
    "working_dir": os.getcwd(),
    "shell": os.environ.get("SHELL", "Unknown")
}

# Prepend documentation block to the file
with open(__file__, 'r+') as file:
    content = file.read()
    file.seek(0)
    file.write(f"""
# Agent: {agent_name}
# Timestamp: {iso_timestamp}
# Startup Instructions:
{startup_instructions}
# Runtime Environment:
{runtime_environment}

""")
    file.write(content)

def register_agent(agent_url):
    try:
        # Validate URL format
        result = urlparse(agent_url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL format")

        # Check for private/internal IPs
        ip = ip_address(result.hostname)
        if ip.is_private or ip.is_loopback:
            raise ValueError("Private or internal IP address detected")

        # Perform HEAD request with 5-second timeout
        response = requests.head(agent_url, timeout=5)
        if response.status_code != 200:
            raise ValueError(f"URL is not reachable: {response.status_code}")

        return {"message": "Agent registered successfully", "url": agent_url}

    except (ValueError, AddressValueError) as e:
        return {"error": str(e)}

# Example usage
if __name__ == "__main__":
    result = register_agent("https://example.com")
    print(result)