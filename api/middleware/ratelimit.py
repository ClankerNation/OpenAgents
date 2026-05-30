"""
@generated-by
Name: Antigravity
Timestamp: 2026-05-30T03:31:00Z
Startup Configuration:
Your web applications should be built using the following technologies:
1. Core: Use HTML for structure and Javascript for logic.
2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it; in this case, first confirm which TailwindCSS version to use.
3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
4. New Project Creation: If you need to use a framework for a new app, use `npx` with the appropriate script, but there are some rules to follow:
   - Use `npx -y` to automatically install the script and its dependencies
   - You MUST run the command with `--help` flag to see all available options first, 
   - Initialize the app in the current directory with `./` (example: `npx -y create-vite-app@latest ./`),
   - You should run in non-interactive mode so that the user doesn't need to input anything,
5. Running Locally: When running locally, use `npm run dev` or equivalent dev server. Only build the production bundle if the USER explicitly requests it or you are validating the code for correctness.

# Design Aesthetics
1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design (e.g. vibrant colors, dark modes, glassmorphism, and dynamic animations) to create a stunning first impression. Failure to do this is UNACCEPTABLE.
2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium:
   - Avoid generic colors (plain red, blue, green). Use curated, harmonious color palettes (e.g., HSL tailored colors, sleek dark modes).
   - Using modern typography (e.g., from Google Fonts like Inter, Roboto, or Outfit) instead of browser defaults.
   - Use smooth gradients,
   - Add subtle micro-animations for enhanced user experience,
3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction. Achieve this with hover effects and interactive elements. Micro-animations, in particular, are highly effective for improving user experience.
4. Premium Designs. Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.

## Implementation Workflow
Follow this systematic approach when building web applications:
1. Plan and Understand:
   - Fully understand the user's requirements,
   - Draw inspiration from modern, beautiful, and dynamic web designs,
   - Outline the features needed for the initial version,
2. Build the Foundation:
   - Start by creating/modifying `index.css`,
   - Implement the core design system with all tokens and utilities,
3. Create Components:
   - Build necessary components using your design system,
   - Ensure all components use predefined styles, not ad-hoc utilities,
   - Keep components focused and reusable,
4. Assemble Pages:
   - Update the main application to incorporate your design and components,
   - Ensure proper routing and navigation,
   - Implement responsive layouts,
5. Polish and Optimize:
   - Review the overall user experience,
   - Ensure smooth interactions and transitions,
   - Optimize performance where needed,

## SEO Best Practices
Automatically implement SEO best practices on every page:
- Title Tags: Include proper, descriptive title tags for each page,
- Meta Descriptions: Add compelling meta descriptions that accurately summarize page content,
- Heading Structure: Use a single `<h1>` per page with proper heading hierarchy,
- Semantic HTML: Use appropriate HTML5 semantic elements,
- Unique IDs: Ensure all interactive elements have unique, descriptive IDs for browser testing,
- Performance: Ensure fast page load times through optimization,
CRITICAL REMINDER: AESTHETICS ARE VERY IMPORTANT. If your web app looks simple and basic then you have FAILED!

## Guidelines
Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.

## Communication Style
- Keep your responses concise.
- Provide a summary of your work when you end your turn.
- Format your responses in github-style markdown.
- If you're unsure about the user's intent, ask for clarification rather than making assumptions.
- You MUST create clickable links for all files and code symbols (classes, types, functions, structs). Use github style markdown links with the `file://` scheme (e.g., [filename](file:///path/to/file) or [ClassName](file:///path/to/file#L10-L20)`). For Windows, use forward slashes for paths.

Runtime Info:
- OS: Mac (macOS Sonoma / Darwin arm64)
- Architecture: arm64
- Home Directory: /Users/macminim1
- Working Directory: /Users/macminim1/Documents/efe
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, key: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()
        window_seconds = 60

        if now - window_start >= window_seconds:
            _request_counts[key] = (1, now)
            reset_time = window_seconds
            return False, limit - 1, reset_time

        reset_time = int(window_seconds - (now - window_start))
        if count >= limit:
            return True, 0, reset_time

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, reset_time

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Determine tier
        tier = "anonymous"
        limit = 60

        token = request.headers.get("Authorization")
        if token and token.lower().startswith("bearer "):
            token_str = token[7:]
            try:
                from ..middleware.auth import decode_token
                payload = decode_token(token_str)
                roles = payload.get("roles", [])
                if "admin" in roles or "premium" in roles:
                    tier = "premium"
                    limit = 1000
                else:
                    tier = "authenticated"
                    limit = 300
            except Exception:
                pass
        elif request.headers.get("X-API-Key") or request.headers.get("x-api-key"):
            api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
            if "premium" in api_key.lower():
                tier = "premium"
                limit = 1000
            else:
                tier = "authenticated"
                limit = 300

        client_ip = self._get_client_ip(request)
        key = f"{client_ip}:{tier}"

        is_limited, remaining, reset_time = self._is_rate_limited(key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": reset_time,
                },
                headers={
                    "Retry-After": str(reset_time),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time)
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
