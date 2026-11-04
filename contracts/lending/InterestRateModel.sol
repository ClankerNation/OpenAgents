// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @date 2026-11-04T19:20:00Z
// @platform Verbatim session instructions, first token to the task:
//   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
//   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
//   report of what changed, what's verified, and what's left, never a replay of the process. No
//   filler, no restating the request back, no re-summarizing what you already said, no narrating
//   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
//   because it's right, not because the user said it. Depth is earned."
//   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
//   a working artifact backed by real tool output — not a description of one. Do not stop after
//   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
//   code or produced the requested result."
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
//   or plan to do without actually doing it."
//   "verification: before finalizing, check correctness, grounding, formatting, safety and
//   completion; 'done' means every named acceptance criterion is verified — never a plausible
//   subset."
//   "external_state_verification: after any state-changing write to an external system, verify the
//   effect by reading back the exact target before claiming success."
//   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
//   patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
//   vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
//   process_manage.
// @runtime os=windows arch=x86_64
//   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe
/////
/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
contract InterestRateModel {
    // BUG: No bounds on base rate — admin can set baseRate to any value including
    // extremely high values that make borrowing effectively impossible, or zero
    // which means lenders earn nothing at low utilization
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink; // optimal utilization (e.g., 80% = 0.8e18)

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks

    address public admin;

    event RateParamsUpdated(uint256 baseRate, uint256 multiplier, uint256 jumpMultiplier, uint256 kink);
    /// @notice Emitted on every parameter change with both sides, so monitoring can diff them.
    event RateParametersUpdated(
        uint256 oldBaseRate,
        uint256 oldMultiplier,
        uint256 oldJumpMultiplier,
        uint256 oldKink,
        uint256 newBaseRate,
        uint256 newMultiplier,
        uint256 newJumpMultiplier,
        uint256 newKink
    );

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) {
        admin = msg.sender;
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
    }

    function updateParams(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            multiplier,
            jumpMultiplier,
            kink,
            _baseRate,
            _multiplier,
            _jumpMultiplier,
            _kink
        );

        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    /// @notice Current parameters in one call, so a reader needs one round trip.
    function getParams()
        external
        view
        returns (uint256 currentBaseRate, uint256 currentMultiplier, uint256 currentJumpMultiplier, uint256 currentKink)
    {
        return (baseRate, multiplier, jumpMultiplier, kink);
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        return (totalBorrowed * PRECISION) / totalDeposits;
    }

    // BUG: Division by zero when utilization is 100% — if totalBorrowed == totalDeposits,
    // utilization equals PRECISION which equals kink edge case, and when utilization > kink,
    // the formula (PRECISION - kink) can be zero if kink == PRECISION, causing revert
    // BUG: Rate overflow for extreme utilization — when utilization greatly exceeds kink
    // (e.g., through direct token transfers), excessUtilization * jumpMultiplier can overflow
    // intermediate calculations and produce nonsensical rates
    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        uint256 jumpRate = (excessUtilization * jumpMultiplier) / (PRECISION - kink);

        return normalRate + jumpRate;
    }

    function getSupplyRate(
        uint256 totalBorrowed,
        uint256 totalDeposits,
        uint256 reserveFactor
    ) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);
        uint256 borrowRate = this.getBorrowRate(totalBorrowed, totalDeposits);
        uint256 rateToPool = (borrowRate * (PRECISION - reserveFactor)) / PRECISION;
        return (utilization * rateToPool) / PRECISION;
    }

    function getAnnualRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return this.getBorrowRate(totalBorrowed, totalDeposits) * BLOCKS_PER_YEAR;
    }
}
