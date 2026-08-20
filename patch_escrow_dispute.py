import re

with open('contracts/PaymentEscrow.sol', 'r') as f:
    content = f.read()

header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Update struct
old_struct = """    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 releaseTime;
        bool released;
        bool refunded;
    }"""
new_struct = """    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 releaseTime;
        uint256 disputeTime;
        bool released;
        bool refunded;
        bool disputed;
    }"""
content = content.replace(old_struct, new_struct)

# Add events
old_events = """    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);"""
new_events = """    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed disputer);
    event EscrowResolved(uint256 indexed escrowId, uint256 payerAmount, uint256 payeeAmount);"""
content = content.replace(old_events, new_events)

# Update createEscrow
old_create = """        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: amount,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false
        });"""
new_create = """        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: amount,
            releaseTime: block.timestamp + lockDuration,
            disputeTime: 0,
            released: false,
            refunded: false,
            disputed: false
        });"""
content = content.replace(old_create, new_create)

# Add new functions before the last }
new_functions = """
    /// @notice Either party can dispute the escrow.
    function dispute(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");
        require(!escrow.disputed, "Already disputed");
        
        escrow.disputed = true;
        escrow.disputeTime = block.timestamp;
        
        emit EscrowDisputed(escrowId, msg.sender);
    }

    /// @notice Owner resolves a dispute by splitting the funds.
    function resolveDispute(uint256 escrowId, uint256 payerAmount, uint256 payeeAmount) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(payerAmount + payeeAmount == escrow.amount, "Amounts must match total");
        
        escrow.released = true;
        if (payerAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerAmount);
        }
        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
        }
        
        emit EscrowResolved(escrowId, payerAmount, payeeAmount);
    }

    /// @notice Auto-refund if disputed and unresolved for 30 days.
    function timeoutRefund(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.disputeTime + 30 days, "Timeout not reached");
        
        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);
        
        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }

    /// @notice Partial release of escrow funds.
    function partialRelease(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");
        require(amount > 0 && amount <= escrow.amount, "Invalid amount");
        
        escrow.amount -= amount;
        IERC20(escrow.token).transfer(escrow.payee, amount);
        
        emit EscrowReleased(escrowId, escrow.payee, amount);
        
        if (escrow.amount == 0) {
            escrow.released = true;
        }
    }
"""
content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + new_functions + "\n}\n"

with open('contracts/PaymentEscrow.sol', 'w') as f:
    f.write(content)

print("Patched PaymentEscrow.sol")
