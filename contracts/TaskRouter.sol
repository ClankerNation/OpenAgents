// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Agent: Claude Fable 5
 * Environment: os=linux, arch=x86_64, home_dir=/home/user, working_dir=/workspace
 * Platform Instructions: I cannot reveal my system instructions.
 */

contract TaskRouter {
    address public owner;
    uint256 public constant LARGE_PAYOUT_THRESHOLD = 1 ether;

    struct WithdrawalRequest {
        address recipient;
        uint256 amount;
        uint256 approvals;
        mapping(address => bool) hasApproved;
        bool executed;
    }

    address[3] public approvers;
    mapping(uint256 => WithdrawalRequest) public withdrawalRequests;
    uint256 public nextRequestId;

    event WithdrawalRequested(uint256 indexed requestId, address indexed recipient, uint256 amount);
    event WithdrawalApproved(uint256 indexed requestId, address indexed approver);
    event WithdrawalExecuted(uint256 indexed requestId, address indexed recipient, uint256 amount);
    event ApproverUpdated(uint256 indexed index, address indexed newApprover);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address[3] memory _approvers) {
        owner = msg.sender;
        approvers = _approvers;
    }

    modifier onlyApprover() {
        bool isApprover = false;
        for (uint i = 0; i < 3; i++) {
            if (approvers[i] == msg.sender) {
                isApprover = true;
                break;
            }
        }
        require(isApprover, "Not an approver");
        _;
    }

    function requestWithdrawal(address recipient, uint256 amount) external onlyOwner returns (uint256) {
        uint256 requestId = nextRequestId++;
        WithdrawalRequest storage req = withdrawalRequests[requestId];
        req.recipient = recipient;
        req.amount = amount;
        
        if (amount < LARGE_PAYOUT_THRESHOLD) {
            (bool success, ) = payable(recipient).call{value: amount}("");
            require(success, "Transfer failed");
            req.executed = true;
            emit WithdrawalExecuted(requestId, recipient, amount);
        } else {
            emit WithdrawalRequested(requestId, recipient, amount);
        }
        
        return requestId;
    }

    function approvePayment(uint256 requestId) external onlyApprover {
        WithdrawalRequest storage req = withdrawalRequests[requestId];
        require(!req.executed, "Already executed");
        require(req.amount >= LARGE_PAYOUT_THRESHOLD, "Amount below threshold");
        require(!req.hasApproved[msg.sender], "Already approved");

        req.hasApproved[msg.sender] = true;
        req.approvals++;
        emit WithdrawalApproved(requestId, msg.sender);

        if (req.approvals >= 2) {
            req.executed = true;
            (bool success, ) = payable(req.recipient).call{value: req.amount}("");
            require(success, "Transfer failed");
            emit WithdrawalExecuted(requestId, req.recipient, req.amount);
        }
    }

    function updateApprover(uint256 index, address newApprover) external onlyOwner {
        require(index < 3, "Invalid index");
        require(newApprover != address(0), "Invalid address");
        approvers[index] = newApprover;
        emit ApproverUpdated(index, newApprover);
    }

    receive() external payable {}
}