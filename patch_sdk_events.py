import re

with open('sdk/src/index.ts', 'r') as f:
    content = f.read()

header = """/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
"""
if not content.startswith("/**\n * @contributor-info"):
    content = header + content

method = """
  /**
   * Subscribe to contract events via WebSocket with auto-reconnect.
   * @param contractAddress Address of the contract
   * @param abi Contract ABI
   * @param eventName Name of the event to listen for
   * @param callback Function to call when event is received
   * @param filters Optional indexed parameter filters
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (event: any) => void,
    filters?: Record<string, any>
  ): void {
    const wsUrl = this.config.rpcUrl.replace(/^http/, "ws");
    let wsProvider = new ethers.WebSocketProvider(wsUrl);
    
    const attachListener = (provider: ethers.WebSocketProvider) => {
      const contract = new ethers.Contract(contractAddress, abi, provider);
      
      contract.on(eventName, (...args: any[]) => {
        const event = args[args.length - 1];
        let matchesFilter = true;
        if (filters) {
          for (const [key, value] of Object.entries(filters)) {
            if (event.args && event.args[key] !== value) {
              matchesFilter = false;
              break;
            }
          }
        }
        if (matchesFilter) {
          callback(event);
        }
      });
      
      provider.websocket.on("close", () => {
        setTimeout(() => {
          try {
            const newProvider = new ethers.WebSocketProvider(wsUrl);
            attachListener(newProvider);
          } catch (e) {
            // Reconnect failed
          }
        }, 5000);
      });
    };
    
    attachListener(wsProvider);
  }
"""

content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + method + "\n}\n"

with open('sdk/src/index.ts', 'w') as f:
    f.write(content)
print("Patched sdk/src/index.ts with event subscription")
