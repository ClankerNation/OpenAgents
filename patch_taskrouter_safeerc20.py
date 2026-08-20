import re

with open('contracts/TaskRouter.sol', 'r') as f:
    content = f.read()

header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Add imports
imports = """import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
"""
content = content.replace('import "./AgentRegistry.sol";', 'import "./AgentRegistry.sol";\n' + imports)

# Add using SafeERC20 and state variables
old_contract = """contract TaskRouter {
    AgentRegistry public registry;"""
new_contract = """contract TaskRouter {
    using SafeERC20 for IERC20;

    AgentRegistry public registry;
    IERC20 public rewardToken;
    address public owner;
    uint256 public collectedFees;"""
content = content.replace(old_contract, new_contract)

# Update constructor
old_constructor = """    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }"""
new_constructor = """    constructor(address _registry, uint256 _platformFee, address _rewardToken) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        rewardToken = IERC20(_rewardToken);
        owner = msg.sender;
    }"""
content = content.replace(old_constructor, new_constructor)

# Update createTask
old_create = """    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        require(msg.value > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: msg.value,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, msg.value);
        return taskId;
    }"""
new_create = """    function createTask(string calldata description, uint256 deadline, uint256 rewardAmount) external returns (uint256) {
        require(rewardAmount > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        rewardToken.safeTransferFrom(msg.sender, address(this), rewardAmount);

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: rewardAmount,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, rewardAmount);
        return taskId;
    }"""
content = content.replace(old_create, new_create)

# Update completeTask
old_complete = """        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = msg.sender.call{value: payout}("");
        require(success, "Payout failed");"""
new_complete = """        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;
        collectedFees += fee;

        rewardToken.safeTransfer(msg.sender, payout);"""
content = content.replace(old_complete, new_complete)

# Update cancelTask
old_cancel = """        task.status = TaskStatus.Cancelled;
        (bool success, ) = msg.sender.call{value: task.reward}("");
        require(success, "Refund failed");"""
new_cancel = """        uint256 refundAmount = task.reward;
        task.reward = 0;
        task.status = TaskStatus.Cancelled;
        rewardToken.safeTransfer(msg.sender, refundAmount);"""
content = content.replace(old_cancel, new_cancel)

# Add withdrawFees before the last }
withdraw_fees = """
    function withdrawFees(address to) external {
        require(msg.sender == owner, "Not owner");
        uint256 amount = collectedFees;
        collectedFees = 0;
        rewardToken.safeTransfer(to, amount);
    }
"""
content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + withdraw_fees + "\n}\n"

with open('contracts/TaskRouter.sol', 'w') as f:
    f.write(content)

print("Patched TaskRouter.sol with SafeERC20")
