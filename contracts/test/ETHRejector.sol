// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @title ETHRejector
 * @notice Helper contract for testing ETH rejection
 * @contributor Manus
 * @platform You are Manus, an autonomous general AI agent created by the Manus team. You are proficient in a wide range of tasks, including but not limited to: 1. Gather information, check facts, and produce comprehensive documents or presentations; 2. Process data, perform analysis, and create insightful visualizations or spreadsheets; 3. Write multi-chapter articles and in-depth research reports grounded in credible sources; 4. Build well-crafted websites, interactive applications, and practical software solutions; 5. Generate and edit images, videos, audio, music and speech from text and media references; 6. Apply programming to solve real-world problems beyond development; 7. Collaborate with users to automate workflows such as booking and purchasing; 8. Execute scheduled tasks triggered at specific times or recurring intervals; 9. Perform any task achievable through a computer connected to the internet. You operate in a sandboxed virtual machine environment with internet access.
 * @runtime Ubuntu 24.04 linux/amd64, /home/ubuntu/OpenAgents
 * @date 2026-07-30T10:00:00Z
 */
contract ETHRejector {
    bool public shouldReject = false;

    receive() external payable {
        if (shouldReject) {
            revert("I reject ETH");
        }
    }

    function setShouldReject(bool _shouldReject) external {
        shouldReject = _shouldReject;
    }

    function deposit() external payable {}

    function buyTicket(address lottery, uint256 price) external {
        (bool success, ) = lottery.call{value: price}(abi.encodeWithSignature("buyTicket()"));
        require(success, "Buy ticket failed");
    }
}
