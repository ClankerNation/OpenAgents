// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using commit-reveal randomness
/// @dev Players buy tickets, and a committed random winner is selected after the round ends
/**
 * @custom:contributor CodexBaseUSDCHunter
 * @custom:date 2026-08-05
 * @custom:runtime darwin/arm64; shell /bin/zsh
 * @custom:note Private session initialization text is intentionally omitted.
 */
contract RandomLottery {
    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant DRAW_COOLDOWN = 1 hours;

    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public nextRoundAt;
    bytes32 public randomnessCommitment;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingPrizes;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event RandomnessCommitted(uint256 indexed round, bytes32 commitment);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event PrizeClaimed(address indexed winner, address indexed recipient, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        require(_ticketPrice > 0, "RandomLottery: zero ticket price");
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0, "RandomLottery: previous round pending");
        require(block.timestamp >= nextRoundAt, "RandomLottery: draw cooldown");
        require(duration > 0, "RandomLottery: zero duration");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(roundEnd != 0 && block.timestamp < roundEnd, "RandomLottery: round inactive");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function commitRandomness(bytes32 commitment) external onlyOwner {
        require(roundEnd != 0 && block.timestamp < roundEnd, "RandomLottery: round inactive");
        require(commitment != bytes32(0), "RandomLottery: empty commitment");
        require(randomnessCommitment == bytes32(0), "RandomLottery: commitment exists");
        randomnessCommitment = commitment;
        emit RandomnessCommitted(currentRound, commitment);
    }

    function drawWinner(bytes32 secret) external onlyOwner {
        require(roundEnd != 0 && block.timestamp >= roundEnd, "RandomLottery: round not ended");
        require(players.length >= MIN_PARTICIPANTS, "RandomLottery: need 3 players");
        require(randomnessCommitment != bytes32(0), "RandomLottery: missing commitment");
        require(
            keccak256(abi.encodePacked(secret)) == randomnessCommitment,
            "RandomLottery: invalid reveal"
        );

        uint256 randomIndex = uint256(keccak256(abi.encodePacked(secret, currentRound))) % players.length;
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;
        nextRoundAt = block.timestamp + DRAW_COOLDOWN;
        randomnessCommitment = bytes32(0);
        delete players;
        pendingPrizes[winner] += prize;

        emit WinnerSelected(winner, prize, currentRound);
    }

    function claimPrize() external {
        _claimPrize(msg.sender, payable(msg.sender));
    }

    function claimPrizeTo(address payable recipient) external {
        _claimPrize(msg.sender, recipient);
    }

    /// @notice Lets the owner rescue a prize for a contract that rejects direct ETH.
    function rescuePrize(address winner, address payable recipient) external onlyOwner {
        require(recipient != address(0), "RandomLottery: zero recipient");
        _claimPrize(winner, recipient);
    }

    function _claimPrize(address winner, address payable recipient) internal {
        uint256 prize = pendingPrizes[winner];
        require(prize > 0, "RandomLottery: no pending prize");
        pendingPrizes[winner] = 0;
        (bool sent, ) = recipient.call{value: prize}("");
        require(sent, "Transfer failed");
        emit PrizeClaimed(winner, recipient, prize);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
