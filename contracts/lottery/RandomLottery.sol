// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    bool public roundCancelled;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event RoundCancelled(uint256 indexed round);
    event RefundClaimed(address indexed player, uint256 amount);

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
        roundCancelled = false;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function cancelRound() external onlyOwner {
        require(block.timestamp < roundEnd && roundEnd != 0, "Round not active");
        require(!roundCancelled, "Already cancelled");
        roundCancelled = true;
        roundEnd = 0; // stop ticket sales
        emit RoundCancelled(currentRound);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd && !roundCancelled, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled, "Round cancelled");

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

    function claimRefund() external {

        require(roundCancelled, "Round not cancelled");

        uint256 refundAmount = 0;

        for (uint256 i = 0; i < players.length; i++) {

            if (players[i] == msg.sender) {

                refundAmount += ticketPrice;

                players[i] = address(0);

            }

        }

        require(refundAmount > 0, "No tickets found");

        

        (bool sent, ) = msg.sender.call{value: refundAmount}("");

        require(sent, "Refund transfer failed");

        emit RefundClaimed(msg.sender, refundAmount);

    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
