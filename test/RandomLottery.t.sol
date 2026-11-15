// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../contracts/lottery/RandomLottery.sol";

/// @notice Tests for the issue #176 lottery cancellation + refund fix.
/// Proves refunds return each participant's exact contribution, that a
/// cancelled round drains to zero, and that active/completed rounds can
/// never be refunded.
contract RandomLotteryRefundTest is Test {
    RandomLottery private lottery;

    address private alice;
    address private bob;
    address private carol;

    uint256 private constant TICKET = 0.01 ether;
    uint256 private constant DURATION = 1 days;

    function setUp() public {
        lottery = new RandomLottery(TICKET);
        alice = makeAddr("alice");
        bob = makeAddr("bob");
        carol = makeAddr("carol");
        vm.deal(alice, 10 ether);
        vm.deal(bob, 10 ether);
        vm.deal(carol, 10 ether);
    }

    function _buy(address player) internal {
        vm.prank(player);
        lottery.buyTicket{value: TICKET}();
    }

    function _startRound(uint256 minParticipants) internal {
        lottery.startRound(DURATION, minParticipants);
    }

    function _warpPastDeadline() internal {
        vm.warp(lottery.roundEnd() + 1);
    }

    function test_CancelAfterDeadlineRefundsExact() public {
        _startRound(3);
        _buy(alice);
        _buy(bob);
        _warpPastDeadline();

        lottery.cancelLottery();
        assertTrue(lottery.roundCancelled(1));

        uint256 aliceBefore = alice.balance;
        uint256 bobBefore = bob.balance;

        vm.prank(alice);
        lottery.refund(1);
        assertEq(alice.balance - aliceBefore, TICKET);

        vm.prank(bob);
        lottery.refund(1);
        assertEq(bob.balance - bobBefore, TICKET);

        // Remaining balance after all refunds is zero.
        assertEq(address(lottery).balance, 0);
    }

    function test_DoubleRefundReverts() public {
        _startRound(3);
        _buy(alice);
        _warpPastDeadline();
        lottery.cancelLottery();

        vm.prank(alice);
        lottery.refund(1);

        vm.prank(alice);
        vm.expectRevert("Nothing to refund");
        lottery.refund(1);
    }

    function test_CannotCancelBeforeDeadline() public {
        _startRound(3);
        _buy(alice);

        vm.warp(lottery.roundEnd() - 1);
        vm.expectRevert("Deadline not passed");
        lottery.cancelLottery();
    }

    function test_CannotCancelWithEnoughParticipants() public {
        _startRound(3);
        _buy(alice);
        _buy(bob);
        _buy(carol);
        _warpPastDeadline();

        vm.expectRevert("Enough participants");
        lottery.cancelLottery();
    }

    function test_CannotRefundActiveLottery() public {
        _startRound(3);
        _buy(alice);

        vm.prank(alice);
        vm.expectRevert("Lottery not cancelled");
        lottery.refund(1);
    }

    function test_CannotRefundCompletedLottery() public {
        _startRound(3);
        _buy(alice);
        _buy(bob);
        _buy(carol);
        _warpPastDeadline();

        lottery.drawWinner();
        assertTrue(lottery.roundCompleted(1));

        vm.prank(alice);
        vm.expectRevert("Lottery not cancelled");
        lottery.refund(1);
    }

    function test_DrawWithTooFewParticipantsReverts() public {
        _startRound(3);
        _buy(alice);
        _buy(bob);
        _warpPastDeadline();

        vm.expectRevert("Not enough participants");
        lottery.drawWinner();
    }

    function test_DrawWinnerPaysFullPrize() public {
        _startRound(3);
        _buy(alice);
        _buy(bob);
        _buy(carol);
        _warpPastDeadline();

        uint256 poolBefore = address(lottery).balance;
        assertEq(poolBefore, 3 * TICKET);

        lottery.drawWinner();

        address winner = lottery.roundWinners(1);
        assertTrue(winner == alice || winner == bob || winner == carol);
        assertEq(address(lottery).balance, 0);
    }

    function test_MultipleTicketsRefundExact() public {
        _startRound(5);
        _buy(alice);
        _buy(alice);
        _buy(alice);
        _buy(bob);
        _warpPastDeadline();
        lottery.cancelLottery();

        uint256 aliceBefore = alice.balance;
        vm.prank(alice);
        lottery.refund(1);
        assertEq(alice.balance - aliceBefore, 3 * TICKET);

        uint256 bobBefore = bob.balance;
        vm.prank(bob);
        lottery.refund(1);
        assertEq(bob.balance - bobBefore, TICKET);

        assertEq(address(lottery).balance, 0);
    }

    function test_RefundAfterNewRoundStarted() public {
        _startRound(3);
        _buy(alice);
        _warpPastDeadline();
        lottery.cancelLottery();

        // A new round starts; the old round's refund must still work.
        _startRound(2);
        assertEq(lottery.currentRound(), 2);

        uint256 aliceBefore = alice.balance;
        vm.prank(alice);
        lottery.refund(1);
        assertEq(alice.balance - aliceBefore, TICKET);
    }

    function test_CannotCancelTwice() public {
        _startRound(3);
        _buy(alice);
        _warpPastDeadline();
        lottery.cancelLottery();

        vm.expectRevert("No active round");
        lottery.cancelLottery();
    }
}
