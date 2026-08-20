import re

def patch_staking():
    with open('contracts/staking/StakingRewards.sol', 'r') as f:
        content = f.read()
        
    header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
    if not content.startswith("// @contributor-info"):
        content = header + content
        
    content = content.replace(
        'import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";',
        'import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";\nimport "../interfaces/IPermit2.sol";'
    )
    
    content = content.replace(
        'IERC20 public immutable rewardsToken;\n    address public owner;',
        'IERC20 public immutable rewardsToken;\n    IPermit2 public immutable permit2;\n    address public owner;'
    )
    
    content = content.replace(
        'constructor(address _stakingToken, address _rewardsToken) {\n        stakingToken = IERC20(_stakingToken);\n        rewardsToken = IERC20(_rewardsToken);\n        owner = msg.sender;\n    }',
        'constructor(address _stakingToken, address _rewardsToken, address _permit2) {\n        stakingToken = IERC20(_stakingToken);\n        rewardsToken = IERC20(_rewardsToken);\n        permit2 = IPermit2(_permit2);\n        owner = msg.sender;\n    }'
    )
    
    stake_permit = """
    /// @notice Stake tokens using Permit2 signature.
    function stakeWithPermit(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(stakingToken), amount: amount}),
            nonce: nonce,
            deadline: deadline
        });
        
        ISignatureTransfer.SignatureTransferDetails memory transferDetails = ISignatureTransfer.SignatureTransferDetails({
            to: address(this),
            requestedAmount: amount
        });
        
        permit2.permitTransferFrom(permit, transferDetails, msg.sender, signature);
        
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        emit Staked(msg.sender, amount);
    }
"""
    content = content.replace('    /// @notice Withdraw staked tokens.', stake_permit + '\n    /// @notice Withdraw staked tokens.')
    
    with open('contracts/staking/StakingRewards.sol', 'w') as f:
        f.write(content)

def patch_amm():
    with open('contracts/dex/AMMPool.sol', 'r') as f:
        content = f.read()
        
    header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
    if not content.startswith("// @contributor-info"):
        content = header + content
        
    content = content.replace(
        'interface IERC20 {',
        'import "../interfaces/IPermit2.sol";\n\ninterface IERC20 {'
    )
    
    content = content.replace(
        '    IERC20 public tokenB;\n\n    uint256 public reserveA;',
        '    IERC20 public tokenB;\n    IPermit2 public permit2;\n\n    uint256 public reserveA;'
    )
    
    content = content.replace(
        '    constructor(address _tokenA, address _tokenB) {\n        tokenA = IERC20(_tokenA);\n        tokenB = IERC20(_tokenB);\n    }',
        '    constructor(address _tokenA, address _tokenB, address _permit2) {\n        tokenA = IERC20(_tokenA);\n        tokenB = IERC20(_tokenB);\n        permit2 = IPermit2(_permit2);\n    }'
    )
    
    amm_permit = """
    function addLiquidityWithPermit(
        uint256 amountA,
        uint256 amountB,
        uint256 nonceA,
        uint256 deadlineA,
        bytes calldata signatureA,
        uint256 nonceB,
        uint256 deadlineB,
        bytes calldata signatureB
    ) external returns (uint256 lpTokens) {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        ISignatureTransfer.PermitTransferFrom memory permitA = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(tokenA), amount: amountA}),
            nonce: nonceA,
            deadline: deadlineA
        });
        ISignatureTransfer.SignatureTransferDetails memory detailsA = ISignatureTransfer.SignatureTransferDetails({
            to: address(this),
            requestedAmount: amountA
        });
        permit2.permitTransferFrom(permitA, detailsA, msg.sender, signatureA);

        ISignatureTransfer.PermitTransferFrom memory permitB = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(tokenB), amount: amountB}),
            nonce: nonceB,
            deadline: deadlineB
        });
        ISignatureTransfer.SignatureTransferDetails memory detailsB = ISignatureTransfer.SignatureTransferDetails({
            to: address(this),
            requestedAmount: amountB
        });
        permit2.permitTransferFrom(permitB, detailsB, msg.sender, signatureB);

        if (totalLiquidity == 0) {
            lpTokens = _sqrt(amountA * amountB);
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }

        reserveA += amountA;
        reserveB += amountB;
        liquidity[msg.sender] += lpTokens;
        totalLiquidity += lpTokens;

        emit LiquidityAdded(msg.sender, amountA, amountB, lpTokens);
    }
"""
    content = content.replace('    function removeLiquidity', amm_permit + '\n    function removeLiquidity')
    
    with open('contracts/dex/AMMPool.sol', 'w') as f:
        f.write(content)

def patch_lending():
    with open('contracts/lending/LendingPool.sol', 'r') as f:
        content = f.read()
        
    header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
    if not content.startswith("// @contributor-info"):
        content = header + content
        
    content = content.replace(
        'interface IPriceFeed {',
        'import "../interfaces/IPermit2.sol";\n\ninterface IPriceFeed {'
    )
    
    content = content.replace(
        '    IERC20 public borrowToken;\n\n    // BUG:',
        '    IERC20 public borrowToken;\n    IPermit2 public permit2;\n\n    // BUG:'
    )
    
    content = content.replace(
        '    constructor(address _oracle, address _collateralToken, address _borrowToken) {\n        oracle = IPriceFeed(_oracle);\n        collateralToken = IERC20(_collateralToken);\n        borrowToken = IERC20(_borrowToken);\n    }',
        '    constructor(address _oracle, address _collateralToken, address _borrowToken, address _permit2) {\n        oracle = IPriceFeed(_oracle);\n        collateralToken = IERC20(_collateralToken);\n        borrowToken = IERC20(_borrowToken);\n        permit2 = IPermit2(_permit2);\n    }'
    )
    
    lending_permit = """
    function depositWithPermit(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(amount > 0, "Zero amount");
        
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(collateralToken), amount: amount}),
            nonce: nonce,
            deadline: deadline
        });
        
        ISignatureTransfer.SignatureTransferDetails memory transferDetails = ISignatureTransfer.SignatureTransferDetails({
            to: address(this),
            requestedAmount: amount
        });
        
        permit2.permitTransferFrom(permit, transferDetails, msg.sender, signature);
        
        positions[msg.sender].collateralAmount += amount;
        totalDeposits += amount;
        emit Deposited(msg.sender, amount);
    }
"""
    content = content.replace('    function borrow', lending_permit + '\n    function borrow')
    
    with open('contracts/lending/LendingPool.sol', 'w') as f:
        f.write(content)

patch_staking()
patch_amm()
patch_lending()
print("Patched all 3 contracts with Permit2")
