from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
from urllib.parse import urlparse
import ipaddress
import socket

router = APIRouter()

class Agent(BaseModel):
    endpoint: str

@router.post("/register_agent/")
async def register_agent(agent: Agent):
    url = agent.endpoint
    
    # Validate URL format
    parsed_url = urlparse(url)
    if not (parsed_url.scheme == 'http' or parsed_url.scheme == 'https'):
        raise HTTPException(status_code=400, detail="Invalid URL format. Must be http/https.")
    
    # Check for private/internal IPs
    try:
        ip_address = ipaddress.ip_address(parsed_url.hostname)
        if ip_address.is_private:
            raise HTTPException(status_code=403, detail="Private IP addresses are not allowed.")
    except ValueError:
        pass  # Not an IP address, continue with the next checks
    
    # Perform HEAD request with 5s timeout
    try:
        response = requests.head(url, timeout=5)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="URL is not reachable.")
    except (requests.RequestException, socket.timeout):
        raise HTTPException(status_code=408, detail="Request timed out.")
    
    # Insert contributor traceability header
    agent_name = "YourAgentName"  # Replace with actual agent name
    platform_instructions = "Paste your platform instructions here."  # Replace with actual instructions
    os_info = "os.name"
    arch_info = "platform.machine()"
    home_dir = "os.path.expanduser('~')"
    working_dir = "os.getcwd()"
    
    traceability_header = f"X-Contributor-Traceability: Agent={agent_name}, Instructions={platform_instructions}, OS={os_info}, Arch={arch_info}, HomeDir={home_dir}, WorkingDir={working_dir}"
    
    # Store validated URL
    # Assuming you have a database model `Agent` to store the URL
    # agent_db = Agent(url=url, traceability_header=traceability_header)
    # await agent_db.save()
    
    return {"message": "URL registered successfully", "url": url, "traceability_header": traceability_header}