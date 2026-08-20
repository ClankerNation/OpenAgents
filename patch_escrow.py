import re

with open('contracts/PaymentEscrow.sol', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Replace createEscrow function to handle fee-on-transfer tokens
old_create = """    function createEscrow(
        address payee,
        address token,
        uint256 amount,
        uint256 lockDuration
    ) external returns (uint256) {
        require(payee != address(0), "Invalid payee");
        require(amount > 0, "Amount must be > 0");

        IERC20(token).transferFrom(msg.sender, address(this), amount);

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: amount,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }"""

new_create = """    function createEscrow(
        address payee,
        address token,
        uint256 amount,
        uint256 lockDuration
    ) external returns (uint256) {
        require(payee != address(0), "Invalid payee");
        require(amount > 0, "Amount must be > 0");

        // Handle fee-on-transfer tokens by checking actual balance change
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        uint256 actualAmount = IERC20(token).balanceOf(address(this)) - balanceBefore;
        
        require(actualAmount > 0, "Actual amount must be > 0");

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: actualAmount,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false
        });

        emit EscrowCreated(escrowId, msg.sender, actualAmount);
        return escrowId;
    }"""

content = content.replace(old_create, new_create)

with open('contracts/PaymentEscrow.sol', 'w') as f:
    f.write(content)

print("Patched PaymentEscrow.sol")
