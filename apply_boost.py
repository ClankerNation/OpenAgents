import re

with open("contracts/staking/StakingRewards.sol", "r") as f:
    content = f.read()

# 1. Add mapping
content = content.replace(
    "mapping(address => uint256) private _balances;",
    "mapping(address => uint256) private _balances;\n    mapping(address => uint256) public stakeStartTime;"
)

# 2. Add getBoostMultiplier
boost_func = """
    function getBoostMultiplier(address account) public view returns (uint256) {
        if (stakeStartTime[account] == 0) return 100;
        uint256 stakedDuration = block.timestamp - stakeStartTime[account];
        if (stakedDuration >= 365 days) return 200; // 2x boost
        if (stakedDuration >= 180 days) return 150; // 1.5x boost
        if (stakedDuration >= 30 days) return 110;  // 1.1x boost
        return 100;
    }

    function lastTimeRewardApplicable() public view returns (uint256) {"""
content = content.replace("    function lastTimeRewardApplicable() public view returns (uint256) {", boost_func)

# 3. Replace earned function
old_earned = """    function earned(address account) public view returns (uint256) {
        return ((_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18) + rewards[account];
    }"""
new_earned = """    function earned(address account) public view returns (uint256) {
        uint256 baseEarned = ((_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18) + rewards[account];
        uint256 boost = getBoostMultiplier(account);
        return (baseEarned * boost) / 100;
    }"""
content = content.replace(old_earned, new_earned)

# 4. Modify stake
old_stake = """    function stake(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }"""
new_stake = """    function stake(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        if (stakeStartTime[msg.sender] == 0) stakeStartTime[msg.sender] = block.timestamp;
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }"""
content = content.replace(old_stake, new_stake)

# 5. Modify withdraw
old_withdraw = """    function withdraw(uint256 amount) public nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot withdraw 0");
        _totalSupply -= amount;
        _balances[msg.sender] -= amount;
        stakingToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }"""
new_withdraw = """    function withdraw(uint256 amount) public nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot withdraw 0");
        _totalSupply -= amount;
        _balances[msg.sender] -= amount;
        if (_balances[msg.sender] == 0) stakeStartTime[msg.sender] = 0;
        stakingToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }"""
content = content.replace(old_withdraw, new_withdraw)

with open("contracts/staking/StakingRewards.sol", "w") as f:
    f.write(content)
