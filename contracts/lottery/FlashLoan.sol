// SPDX-License-Identifier: MIT
/**
 * Contributor: OpenAI-Assistant
 * Platform Init:
 * You are ChatGPT, a large language model trained by OpenAI.
 * Knowledge cutoff: 2024-06
 * Current date: 2026-11-01
 * Runtime: OS=Ubuntu 22.04, Arch=x86_64, CWD=/home/assistant/OpenAgents, Shell=bash
 */

pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/interfaces/IERC3156FlashBorrower.sol";
import "@openzeppelin/contracts/interfaces/IERC3156FlashLender.sol";

/**
 * @title FlashLoan
 * @dev ERC-3156 compliant flash loan provider with minimum fee enforcement,
 *      a 50% loan cap relative to the pool balance, rebasing-safe accounting and
 *      emergency pause functionality.
 */
contract FlashLoan is IERC3156FlashLender, Ownable, Pausable {
    // Token that can be flash-loaned
    IERC20 public immutable token;

    // Fee rate expressed in basis points (e.g. 0.05% = 5 basis points)
    uint256 public feeBasisPoints;

    // Minimum fee expressed in token smallest units (1 token = 10**decimals)
    uint256 public immutable minFee;

    // ERC-3156 constant
    uint256 public constant MAX_BASIS_POINTS = 10_000;

    // Events
    event FeeBasisPointsUpdated(uint256 newFeeBP);
    event FlashLoanExecuted(address borrower, uint256 amount, uint256 fee);

    /**
     * @dev Constructor sets the token, fee rate and computes the minimum fee.
     * @param _token Address of the ERC20 token to be flash-loaned.
     * @param _feeBasisPoints Fee expressed in basis points (1 bp = 0.01%).
     */
    constructor(IERC20 _token, uint256 _feeBasisPoints) Ownable(msg.sender) {
        require(address(_token) != address(0), "FlashLoan: token zero address");
        token = _token;
        feeBasisPoints = _feeBasisPoints;
        // Determine token decimals for a 1-token minimum fee
        uint8 decimals = 18;
        try IERC20Metadata(address(_token)).decimals() returns (uint8 d) {
            decimals = d;
        } catch {}
        minFee = 10 ** decimals; // 1 token in smallest unit
    }

    /**
     * @dev Update the fee basis points. Only owner can call.
     */
    function setFeeBasisPoints(uint256 _feeBasisPoints) external onlyOwner {
        require(_feeBasisPoints <= MAX_BASIS_POINTS, "FlashLoan: fee too high");
        feeBasisPoints = _feeBasisPoints;
        emit FeeBasisPointsUpdated(_feeBasisPoints);
    }

    /**
     * @dev Pause the contract – emergency stop. Only owner.
     */
    function pause() external onlyOwner {
        _pause();
    }

    /**
     * @dev Unpause the contract. Only owner.
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    /**
     * @dev ERC-3156 maxFlashLoan – returns the maximum amount that can be borrowed.
     *      The cap is 50% of the current token balance held by this contract.
     */
    function maxFlashLoan(address tokenAddress) external view override returns (uint256) {
        if (tokenAddress != address(token)) {
            return 0;
        }
        uint256 poolBalance = token.balanceOf(address(this));
        return poolBalance / 2; // 50% of pool
    }

    /**
     * @dev ERC-3156 flashFee – calculates the fee for a given amount.
     *      Fee = max(amount * feeBasisPoints / 10_000, minFee).
     */
    function flashFee(address tokenAddress, uint256 amount) public view override returns (uint256) {
        require(tokenAddress == address(token), "FlashLoan: unsupported token");
        uint256 fee = (amount * feeBasisPoints) / MAX_BASIS_POINTS;
        if (fee < minFee) {
            fee = minFee;
        }
        return fee;
    }

    /**
     * @dev ERC-3156 flashLoan implementation.
     *      Enforces the 50% cap, minimum fee, rebasing-safe accounting and pause.
     */
    function flashLoan(
        IERC3156FlashBorrower receiver,
        address tokenAddress,
        uint256 amount,
        bytes calldata data
    ) external override whenNotPaused returns (bool) {
        require(tokenAddress == address(token), "FlashLoan: unsupported token");
        uint256 maxLoan = this.maxFlashLoan(tokenAddress);
        require(amount <= maxLoan, "FlashLoan: amount exceeds 50% cap");

        uint256 fee = flashFee(tokenAddress, amount);
        uint256 balanceBefore = token.balanceOf(address(this));
        require(balanceBefore >= amount, "FlashLoan: insufficient liquidity");

        // Transfer the loan amount to the borrower
        token.transfer(address(receiver), amount);

        // Callback to the borrower
        require(
            receiver.onFlashLoan(msg.sender, tokenAddress, amount, fee, data) ==
                keccak256("ERC3156FlashBorrower.onFlashLoan"),
            "FlashLoan: callback failed"
        );

        // Borrower must have approved the fee transfer back to this contract
        uint256 balanceAfter = token.balanceOf(address(this));
        require(
            balanceAfter >= balanceBefore + fee,
            "FlashLoan: insufficient repayment"
        );

        emit FlashLoanExecuted(address(receiver), amount, fee);
        return true;
    }
}
