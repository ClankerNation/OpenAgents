import re

with open('contracts/staking/MultiTokenStaking.sol', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Add event
event_add = """    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);
    event EmergencyWithdraw(address indexed user, uint256 indexed pid, uint256 amount);"""
content = content.replace("    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);", event_add)

# Add emergencyWithdraw function before the last }
emergency_fn = """
    /// @notice Withdraw staked tokens without caring about rewards. Emergency use only.
    /// @param pid Pool ID.
    function emergencyWithdraw(uint256 pid) external nonReentrant {
        PoolInfo storage pool = poolInfo[pid];
        UserInfo storage user = userInfo[pid][msg.sender];
        uint256 amount = user.amount;
        require(amount > 0, "MultiStaking: nothing staked");

        user.amount = 0;
        user.rewardDebt = 0;
        pool.totalStaked -= amount;

        pool.stakeToken.safeTransfer(msg.sender, amount);
        emit EmergencyWithdraw(msg.sender, pid, amount);
    }
"""

content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + emergency_fn + "\n}\n"

with open('contracts/staking/MultiTokenStaking.sol', 'w') as f:
    f.write(content)

print("Patched MultiTokenStaking.sol")
