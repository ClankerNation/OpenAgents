// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract GovernorAlphaTestToken {
    mapping(address => uint256) public votes;
    mapping(address => mapping(uint256 => uint256)) public pastVotes;

    function setVotes(address account, uint256 amount) external {
        votes[account] = amount;
    }

    function setPastVotes(address account, uint256 blockNumber, uint256 amount) external {
        pastVotes[account][blockNumber] = amount;
    }

    function getVotes(address account) external view returns (uint256) {
        return votes[account];
    }

    function getPastVotes(address account, uint256 blockNumber) external view returns (uint256) {
        return pastVotes[account][blockNumber];
    }
}
