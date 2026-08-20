import re

with open('contracts/staking/StakingRewards.sol', 'r') as f:
    content = f.read()

header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

with open('contracts/staking/StakingRewards.sol', 'w') as f:
    f.write(content)

print("Patched StakingRewards.sol")
