// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/dex/AMMPool.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    constructor(string memory name, string memory symbol) ERC20(name, symbol) {}
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract AMMPoolTest is Test {
    AMMPool pool;
    MockERC20 token0;
    MockERC20 token1;
    address user1 = address(0x1);
    address user2 = address(0x2);

    function setUp() public {
        token0 = new MockERC20("Token 0", "TK0");
        token1 = new MockERC20("Token 1", "TK1");
        pool = new AMMPool(address(token0), address(token1));
        
        token0.mint(user1, 1000 ether);
        token1.mint(user1, 1000 ether);
        token0.mint(user2, 1000 ether);
        token1.mint(user2, 1000 ether);
        
        vm.prank(user1); token0.approve(address(pool), type(uint256).max);
        vm.prank(user1); token1.approve(address(pool), type(uint256).max);
        vm.prank(user2); token0.approve(address(pool), type(uint256).max);
        vm.prank(user2); token1.approve(address(pool), type(uint256).max);
    }

    function testFirstDepositLocksMinimumLiquidity() public {
        vm.prank(user1);
        pool.addLiquidity(10 ether, 10 ether);
        
        assertEq(pool.balanceOf(address(0)), 1000);
        assertEq(pool.totalSupply(), 10 ether + 1000);
    }

    function testRemoveLiquidityUsesInternalReserves() public {
        vm.prank(user1);
        pool.addLiquidity(10 ether, 10 ether);
        
        token0.mint(address(pool), 100 ether);
        token1.mint(address(pool), 100 ether);
        
        uint256 lpBalance = pool.balanceOf(user1);
        uint256 totalSupply = pool.totalSupply();
        
        (uint112 res0, uint112 res1,) = pool.getReserves();
        
        uint256 expected0 = (lpBalance * res0) / totalSupply;
        uint256 expected1 = (lpBalance * res1) / totalSupply;
        
        vm.prank(user1);
        pool.removeLiquidity(lpBalance, user1);
        
        assertEq(token0.balanceOf(user1), 1000 ether - 10 ether + expected0);
        assertEq(token1.balanceOf(user1), 1000 ether - 10 ether + expected1);
    }

    function testSync() public {
        vm.prank(user1);
        pool.addLiquidity(10 ether, 10 ether);
        
        token0.mint(address(pool), 5 ether);
        
        pool.sync();
        
        (uint112 res0, uint112 res1,) = pool.getReserves();
        assertEq(res0, 15 ether);
    }
}
