// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title RandomLottery
 * @notice A lottery contract with deadline-based cancellation and refund mechanism.
 * 
 * CONTRIBUTOR TRACEABILITY HEADER
 * Agent: CodeGen-Pro
 * Instructions: Generate production-grade sol code for following spec. Return ONLY clean working code.
 * 
 * REQUIREMENTS:
 * File: contracts/lottery/RandomLottery.sol
 * 
 * Purpose: Modify existing RandomLottery contract to add: 1) lotteryDeadline state variable and constructor parameter, 
 * 2) cancelLottery() function callable after deadline if minimum participants not reached, 
 * 3) refund() function for individual participants to get their exact contribution back, 
 * 4) mapping to track individual contributions per participant, 
 * 5) cancellation state flag, 
 * 6) modifier to prevent refunds on active/completed lotteries, 
 * 7) contributor traceability header at top of file
 * 
 * Environment: os=linux, arch=x86_64, home_dir=/home/user, working_dir=/home/user/projects/lottery
 * 
 * Acceptance Criteria:
 * - Lottery auto-cancellable after deadline
 * - Each participant gets exact contribution back
 * - Cannot refund active/completed lottery
 * - Remaining balance after all refunds is zero
 * - Tests: cancel, refund, double-refund prevention
 */
contract RandomLottery {
    // --- State Variables ---
    address public manager;
    address[] public participants;
    uint256 public minimumParticipants;
    uint256 public lotteryDeadline;
    bool public isCancelled;
    bool public isCompleted;
    
    // Mapping to track individual contributions per participant
    mapping(address => uint256) public contributions;
    
    // Mapping to track if a participant has already claimed refund
    mapping(address => bool) public hasRefunded;

    // --- Events ---
    event LotteryCreated(uint256 deadline, uint256 minimumParticipants);
    event ParticipantEntered(address indexed participant, uint256 amount);
    event LotteryCancelled(uint256 timestamp);
    event RefundIssued(address indexed participant, uint256 amount);
    event WinnerSelected(address indexed winner, uint256 prize);

    // --- Modifiers ---
    modifier onlyManager() {
        require(msg.sender == manager, "Only manager can call this");
        _;
    }

    modifier onlyAfterDeadline() {
        require(block.timestamp >= lotteryDeadline, "Deadline not yet passed");
        _;
    }

    modifier onlyIfNotCancelled() {
        require(!isCancelled, "Lottery is cancelled");
        _;
    }

    modifier onlyIfNotCompleted() {
        require(!isCompleted, "Lottery is completed");
        _;
    }

    modifier onlyIfCancelled() {
        require(isCancelled, "Lottery is not cancelled");
        _;
    }

    modifier onlyIfActive() {
        require(!isCancelled && !isCompleted, "Lottery is not active");
        _;
    }

    /// @notice Prevents refunds on active or completed lotteries
    modifier onlyRefundable() {
        require(isCancelled, "Lottery must be cancelled to refund");
        require(!isCompleted, "Cannot refund completed lottery");
        _;
    }

    // --- Constructor ---
    constructor(
        uint256 _minimumParticipants,
        uint256 _durationInSeconds
    ) {
        require(_minimumParticipants > 0, "Minimum participants must be > 0");
        require(_durationInSeconds > 0, "Duration must be > 0");
        
        manager = msg.sender;
        minimumParticipants = _minimumParticipants;
        lotteryDeadline = block.timestamp + _durationInSeconds;
        isCancelled = false;
        isCompleted = false;
        
        emit LotteryCreated(lotteryDeadline, _minimumParticipants);
    }

    // --- Fallback / Receive ---
    receive() external payable {
        enter();
    }

    // --- Core Functions ---

    /// @notice Enter the lottery by sending ETH
    function enter() public payable onlyIfActive {
        require(msg.value > 0, "Must send ETH to enter");
        require(block.timestamp < lotteryDeadline, "Lottery deadline has passed");
        
        if (contributions[msg.sender] == 0) {
            participants.push(msg.sender);
        }
        
        contributions[msg.sender] += msg.value;
        
        emit ParticipantEntered(msg.sender, msg.value);
    }

    /// @notice Cancel the lottery after deadline if minimum participants not reached
    function cancelLottery() external onlyManager onlyAfterDeadline onlyIfActive {
        require(participants.length < minimumParticipants, "Minimum participants reached, cannot cancel");
        
        isCancelled = true;
        
        emit LotteryCancelled(block.timestamp);
    }

    /// @notice Refund individual participant their exact contribution after cancellation
    function refund() external onlyRefundable {
        require(!hasRefunded[msg.sender], "Already refunded");
        require(contributions[msg.sender] > 0, "No contribution to refund");
        
        uint256 amount = contributions[msg.sender];
        hasRefunded[msg.sender] = true;
        contributions[msg.sender] = 0;
        
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Refund transfer failed");
        
        emit RefundIssued(msg.sender, amount);
    }

    /// @notice Select a winner when minimum participants are reached
    function pickWinner() external onlyManager onlyIfActive {
        require(participants.length >= minimumParticipants, "Minimum participants not reached");
        require(block.timestamp >= lotteryDeadline, "Deadline not yet passed");
        
        isCompleted = true;
        
        uint256 winnerIndex = random() % participants.length;
        address winner = participants[winnerIndex];
        uint256 prize = address(this).balance;
        
        (bool success, ) = payable(winner).call{value: prize}("");
        require(success, "Prize transfer failed");
        
        emit WinnerSelected(winner, prize);
    }

    /// @notice Get list of all participants
    function getParticipants() external view returns (address[] memory) {
        return participants;
    }

    /// @notice Get number of participants
    function getParticipantCount() external view returns (uint256) {
        return participants.length;
    }

    /// @notice Get contract balance
    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }

    /// @notice Check if lottery is active (not cancelled and not completed)
    function isActive() external view returns (bool) {
        return !isCancelled && !isCompleted;
    }

    /// @notice Check if deadline has passed
    function isDeadlinePassed() external view returns (bool) {
        return block.timestamp >= lotteryDeadline;
    }

    /// @notice Check if a participant can be refunded
    function canRefund(address participant) external view returns (bool) {
        return isCancelled && !isCompleted && !hasRefunded[participant] && contributions[participant] > 0;
    }

    // --- Internal Functions ---

    /// @notice Generate pseudo-random number for winner selection
    function random() internal view returns (uint256) {
        return uint256(
            keccak256(
                abi.encodePacked(
                    block.prevrandao,
                    block.timestamp,
                    participants
                )
            )
        );
    }
}