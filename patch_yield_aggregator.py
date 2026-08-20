import re

with open('contracts/vault/YieldAggregator.sol', 'r') as f:
    content = f.read()

header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Fix deposit
old_deposit = """    function deposit(uint256 amount) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");

        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            sharesMinted = (amount * totalShares) / totalAssets();
        }

        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesMinted;
        totalDeposited += amount;
        shares[msg.sender] += sharesMinted;

        emit Deposit(msg.sender, amount, sharesMinted);
    }"""

new_deposit = """    function deposit(uint256 amount, uint256 minShares) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");

        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            sharesMinted = (amount * totalShares) / totalDeposited;
        }
        require(sharesMinted >= minShares, "Vault: slippage exceeded");

        // Share price sanity check (max 5% deviation)
        if (totalShares > 0 && totalDeposited > 0) {
            uint256 currentPrice = (totalDeposited * 1e18) / totalShares;
            uint256 expectedPrice = (amount * 1e18) / sharesMinted;
            require(currentPrice <= expectedPrice * 105 / 100, "Vault: price deviation > 5%");
        }

        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesMinted;
        totalDeposited += amount;
        shares[msg.sender] += sharesMinted;

        emit Deposit(msg.sender, amount, sharesMinted);
    }"""

content = content.replace(old_deposit, new_deposit)

# Fix withdraw
old_withdraw = """    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 assetsReturned) {
        require(shareAmount > 0, "Vault: zero shares");
        require(shares[msg.sender] >= shareAmount, "Vault: insufficient shares");

        // BUG: Uses balanceOf instead of internal accounting (totalDeposited + strategy gains).
        // If tokens are donated directly to the vault or a strategy returns funds outside
        // the normal flow, this inflates the withdrawal amount, allowing early withdrawers
        // to drain more than their share at the expense of later users.
        assetsReturned = (shareAmount * asset.balanceOf(address(this))) / totalShares;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }"""

new_withdraw = """    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 assetsReturned) {
        require(shareAmount > 0, "Vault: zero shares");
        require(shares[msg.sender] >= shareAmount, "Vault: insufficient shares");

        // Use internal accounting (totalDeposited) to prevent donation attacks
        assetsReturned = (shareAmount * totalDeposited) / totalShares;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalDeposited -= assetsReturned;

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }"""

content = content.replace(old_withdraw, new_withdraw)

# Fix addStrategy
old_add = """    function addStrategy(address target) external onlyOwner {
        strategies.push(Strategy({
            target: target,
            allocated: 0,
            active: true
        }));
        emit StrategyAdded(strategies.length - 1, target);
    }"""

new_add = """    function addStrategy(address target) external onlyOwner {
        require(target != address(0), "Vault: zero address strategy");
        strategies.push(Strategy({
            target: target,
            allocated: 0,
            active: true
        }));
        emit StrategyAdded(strategies.length - 1, target);
    }"""

content = content.replace(old_add, new_add)

# Fix previewDeposit
old_preview = """    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        return (amount * totalShares) / totalAssets();
    }"""

new_preview = """    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        return (amount * totalShares) / totalDeposited;
    }"""

content = content.replace(old_preview, new_preview)

with open('contracts/vault/YieldAggregator.sol', 'w') as f:
    f.write(content)

print("Patched YieldAggregator.sol")
