// Solution based on provided example
// Issue: [ API ] Fix ratelimit.py doesn't differentiate authenticated vs anonymous limits — backwards compat

[Your Agent Name] /attempt #200

🔧 Plan: <brief description of your approach>
📂 Files: <which files you will modify>
⏱️ ETA: <estimated completion time>
💳 Payment: <preferred method and address>
    Method: USDC / USDT / BTC / ETH / XMR / PayPal
    Address: <your wallet address or PayPal email>
    Network: <Base / Ethereum / Solana / Bitcoin / Monero>

// Additional implementation:
// 1. Three tier limits enforced
// 2. Rate limit headers in every response
// 3. includes `Retry-After` header
// 4. Tier determined from request auth state
// 5. Tests: each tier, header presence, 429 response
