// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]


/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        // BUG: No minimum participants check — if only 1 player entered,
        // the lottery is pointless and the single player always wins their own funds minus gas
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    // --- Timelock Ownership (2-day delay) ---
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;
    uint256 public constant TIMELOCK_DELAY = 2 days;

    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner, uint256 executeAfter);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledNewOwner);
    event OwnershipAccepted(address indexed previousOwner, address indexed newOwner);

    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "New owner is zero");
        require(newOwner != owner, "Already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferInitiated(owner, newOwner, block.timestamp + TIMELOCK_DELAY);
    }

    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Not pending owner");
        require(_transferInitiatedAt > 0, "No pending transfer");
        require(block.timestamp >= _transferInitiatedAt + TIMELOCK_DELAY, "Timelock not expired");
        address oldOwner = owner;
        owner = msg.sender;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipAccepted(oldOwner, msg.sender);
    }

    function cancelTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "No pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(owner, cancelled);
    }

    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    function transferInitiatedAt() external view returns (uint256) {
        return _transferInitiatedAt;
    }

}
