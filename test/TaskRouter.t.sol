// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../contracts/AgentRegistry.sol";
import "../contracts/TaskRouter.sol";
import "../contracts/mocks/MockToken.sol";

/// @notice Tests for the issue #181 SafeERC20 fix in TaskRouter.
/// Proves balances actually moved (not just that a function returned),
/// that a `false`-returning token reverts the whole transaction, and
/// that the original ETH flow is unchanged.
contract TaskRouterSafeERC20Test is Test {
    AgentRegistry private registry;
    TaskRouter private router;
    MockToken private token;

    address private constant CREATOR = address(0xC4EA704);
    address private constant AGENT_OWNER = address(0xA6E17);
    address private constant STRANGER = address(0x57A46E4);
    uint256 private constant REWARD = 1000 ether;
    uint256 private constant FEE_BPS = 500; // 5%
    uint256 private constant FEE = 50 ether;
    uint256 private constant PAYOUT = 950 ether;

    bytes32 private agentId;

    receive() external payable {}

    function setUp() public {
        registry = new AgentRegistry(0);
        router = new TaskRouter(address(registry), FEE_BPS);
        token = new MockToken();

        vm.prank(AGENT_OWNER);
        agentId = registry.registerAgent("agent-1", "https://example.com");
    }

    function _createERC20Task() internal returns (uint256) {
        token.mint(CREATOR, REWARD);
        vm.prank(CREATOR);
        token.approve(address(router), REWARD);
        vm.prank(CREATOR);
        return router.createTaskERC20("do work", block.timestamp + 1 days, address(token), REWARD);
    }

    function _assign(uint256 taskId) internal {
        vm.prank(AGENT_OWNER);
        router.assignTask(taskId, agentId);
    }

    function testERC20FullFlowPaysStandardToken() public {
        uint256 taskId = _createERC20Task();
        assertEq(token.balanceOf(address(router)), REWARD, "escrow funded");
        _assign(taskId);

        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        assertEq(token.balanceOf(AGENT_OWNER), PAYOUT, "agent receives payout");
        assertEq(token.balanceOf(address(router)), FEE, "only the fee stays escrowed");
        assertEq(router.feesCollected(address(token)), FEE, "fee is tracked");
        (,,,,, TaskRouter.TaskStatus status,,,) = router.tasks(taskId);
        assertEq(uint256(status), uint256(TaskRouter.TaskStatus.Completed), "task completed");
    }

    function testERC20CompleteRevertsOnFalseReturnToken() public {
        token.setFailTransfer(true);
        uint256 taskId = _createERC20Task();
        _assign(taskId);

        vm.expectRevert(
            abi.encodeWithSelector(SafeERC20.SafeERC20FailedOperation.selector, address(token))
        );
        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        // Whole transaction reverted: nothing was paid, task still assigned,
        // escrow intact — the exact failure the issue describes as silent.
        (,,,,, TaskRouter.TaskStatus status,,,) = router.tasks(taskId);
        assertEq(uint256(status), uint256(TaskRouter.TaskStatus.Assigned), "task stays assigned");
        assertEq(token.balanceOf(AGENT_OWNER), 0, "agent received nothing");
        assertEq(token.balanceOf(address(router)), REWARD, "escrow intact");
        assertEq(router.feesCollected(address(token)), 0, "no fee recorded");
    }

    function testERC20CancelRevertsOnFalseReturnToken() public {
        token.setFailTransfer(true);
        uint256 taskId = _createERC20Task();

        vm.expectRevert(
            abi.encodeWithSelector(SafeERC20.SafeERC20FailedOperation.selector, address(token))
        );
        vm.prank(CREATOR);
        router.cancelTask(taskId);

        (,,,,, TaskRouter.TaskStatus status,,,) = router.tasks(taskId);
        assertEq(uint256(status), uint256(TaskRouter.TaskStatus.Open), "task stays open");
        assertEq(token.balanceOf(CREATOR), 0, "creator not refunded");
        assertEq(token.balanceOf(address(router)), REWARD, "escrow intact");
    }

    function testERC20CreateRevertsOnFalseReturnFrom() public {
        token.setFailTransferFrom(true);
        token.mint(CREATOR, REWARD);
        vm.prank(CREATOR);
        token.approve(address(router), REWARD);

        vm.expectRevert(
            abi.encodeWithSelector(SafeERC20.SafeERC20FailedOperation.selector, address(token))
        );
        vm.prank(CREATOR);
        router.createTaskERC20("do work", block.timestamp + 1 days, address(token), REWARD);

        assertEq(router.taskCount(), 0, "no task created without escrow");
        assertEq(token.balanceOf(address(router)), 0, "no escrow taken");
    }

    function testERC20NoReturnTokenEndToEnd() public {
        token.setNoReturn(true);
        uint256 taskId = _createERC20Task();
        _assign(taskId);

        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        // SafeERC20 tolerates the empty returndata of legacy tokens.
        assertEq(token.balanceOf(AGENT_OWNER), PAYOUT, "agent receives payout");
        assertEq(token.balanceOf(address(router)), FEE, "only the fee stays escrowed");
    }

    function testETHFlowRegression() public {
        vm.deal(CREATOR, 1 ether);
        vm.prank(CREATOR);
        uint256 taskId = router.createTask{value: 1 ether}("do work", block.timestamp + 1 days);
        _assign(taskId);

        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        assertEq(AGENT_OWNER.balance, 0.95 ether, "agent receives ETH payout");
        assertEq(router.feesCollectedETH(), 0.05 ether, "ETH fee is tracked");
        assertEq(address(router).balance, 0.05 ether, "only the fee stays in the router");
    }

    function testETHCancelRefunds() public {
        vm.deal(CREATOR, 1 ether);
        vm.prank(CREATOR);
        uint256 taskId = router.createTask{value: 1 ether}("do work", block.timestamp + 1 days);

        vm.prank(CREATOR);
        router.cancelTask(taskId);

        assertEq(CREATOR.balance, 1 ether, "creator refunded in full");
        assertEq(address(router).balance, 0, "router holds nothing");
    }

    function testWithdrawFeesERC20OnlyAdminAndOnlyFees() public {
        uint256 taskId = _createERC20Task();
        _assign(taskId);
        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        // A second task's escrow must never be withdrawable as "fees".
        _createERC20Task();

        vm.expectRevert("Not admin");
        vm.prank(STRANGER);
        router.withdrawFees(address(token));

        uint256 adminBefore = token.balanceOf(address(this));
        router.withdrawFees(address(token));

        assertEq(token.balanceOf(address(this)), adminBefore + FEE, "admin gets exactly the fee");
        assertEq(token.balanceOf(address(router)), REWARD, "open task escrow untouched");
        assertEq(router.feesCollected(address(token)), 0, "fee accounting cleared");

        vm.expectRevert("No fees");
        router.withdrawFees(address(token));
    }

    function testWithdrawFeesETH() public {
        vm.deal(CREATOR, 2 ether);
        vm.prank(CREATOR);
        uint256 taskId = router.createTask{value: 1 ether}("do work", block.timestamp + 1 days);
        _assign(taskId);
        vm.prank(AGENT_OWNER);
        router.completeTask(taskId, "done");

        // Second task's ETH escrow must stay put.
        vm.prank(CREATOR);
        router.createTask{value: 1 ether}("more work", block.timestamp + 1 days);

        router.withdrawFees(address(0));

        assertEq(address(router).balance, 1 ether, "open task escrow untouched");
        assertEq(router.feesCollectedETH(), 0, "ETH fee accounting cleared");
    }

    function testWithdrawFeesRevertsWithNoFees() public {
        vm.expectRevert("No fees");
        router.withdrawFees(address(token));
        vm.expectRevert("No fees");
        router.withdrawFees(address(0));
    }
}
