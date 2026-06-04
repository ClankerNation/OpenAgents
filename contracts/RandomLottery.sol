// Agent: CodeFixerAI
// Instructions: You are an expert Solidity developer. Fix the RandomLottery contract to add refund functionality. The contract must allow cancellation after deadline if minimum participants not reached, allow participants to claim refunds, track individual contributions, and prevent refunds for active/completed lotteries. Include all necessary state variables, events, and modifiers. Ensure the contract compiles with Solidity ^0.8.0.
// Environment: os=linux, arch=x86_64, home_dir=/home/user, working_dir=/home/user/project

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract RandomLottery {
    address public manager;
    address[] public participants;
    mapping(address => uint256) public contributions;
    uint256 public minimumParticipants;
    uint256 public lotteryDeadline;
    bool public lotteryCancelled;
    bool public lotteryCompleted;
    uint256 public totalCollected;
    
    event LotteryCreated(uint256 deadline, uint256 minParticipants);
    event ParticipantEntered(address indexed participant, uint256 amount);
    event LotteryCancelled(uint256 timestamp);
    event RefundIssued(address indexed participant, uint256 amount);
    event WinnerSelected(address indexed winner, uint256 amount);
    
    modifier onlyManager() {
        require(msg.sender == manager, "Only manager can call this");
        _;
    }
    
    modifier lotteryActive() {
        require(!lotteryCancelled, "Lottery is cancelled");
        require(!lotteryCompleted, "Lottery is completed");
        require(block.timestamp < lotteryDeadline, "Lottery deadline passed");
        _;
    }
    
    modifier lotteryEnded() {
        require(block.timestamp >= lotteryDeadline, "Lottery still active");
        _;
    }
    
    constructor(uint256 _minimumParticipants, uint256 _durationInSeconds) {
        require(_minimumParticipants > 0, "Minimum participants must be > 0");
        require(_durationInSeconds > 0, "Duration must be > 0");
        
        manager = msg.sender;
        minimumParticipants = _minimumParticipants;
        lotteryDeadline = block.timestamp + _durationInSeconds;
        lotteryCancelled = false;
        lotteryCompleted = false;
        totalCollected = 0;
        
        emit LotteryCreated(lotteryDeadline, _minimumParticipants);
    }
    
    function enter() public payable lotteryActive {
        require(msg.value > 0, "Must send ETH to enter");
        
        if (contributions[msg.sender] == 0) {
            participants.push(msg.sender);
        }
        
        contributions[msg.sender] += msg.value;
        totalCollected += msg.value;
        
        emit ParticipantEntered(msg.sender, msg.value);
    }
    
    function cancelLottery() public onlyManager lotteryEnded {
        require(!lotteryCancelled, "Already cancelled");
        require(!lotteryCompleted, "Already completed");
        require(participants.length < minimumParticipants, "Minimum participants reached");
        
        lotteryCancelled = true;
        emit LotteryCancelled(block.timestamp);
    }
    
    function refund() public {
        require(lotteryCancelled, "Lottery not cancelled");
        require(contributions[msg.sender] > 0, "No contribution to refund");
        
        uint256 amount = contributions[msg.sender];
        contributions[msg.sender] = 0;
        totalCollected -= amount;
        
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Refund failed");
        
        emit RefundIssued(msg.sender, amount);
    }
    
    function selectWinner() public onlyManager lotteryEnded {
        require(!lotteryCancelled, "Lottery is cancelled");
        require(!lotteryCompleted, "Already completed");
        require(participants.length >= minimumParticipants, "Not enough participants");
        
        lotteryCompleted = true;
        
        uint256 winnerIndex = uint256(keccak256(abi.encodePacked(block.timestamp, block.prevrandao, participants.length))) % participants.length;
        address winner = participants[winnerIndex];
        uint256 prize = address(this).balance;
        
        (bool success, ) = payable(winner).call{value: prize}("");
        require(success, "Prize transfer failed");
        
        emit WinnerSelected(winner, prize);
    }
    
    function getParticipants() public view returns (address[] memory) {
        return participants;
    }
    
    function getBalance() public view returns (uint256) {
        return address(this).balance;
    }
    
    function isLotteryActive() public view returns (bool) {
        return !lotteryCancelled && !lotteryCompleted && block.timestamp < lotteryDeadline;
    }
    
    function canCancel() public view returns (bool) {
        return block.timestamp >= lotteryDeadline && !lotteryCancelled && !lotteryCompleted && participants.length < minimumParticipants;
    }
}