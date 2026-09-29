# Tests for JWT auth: none rejected, env fallback, revocation, refresh.
import sys, os
sys.path.insert(0, ".")
os.environ.pop("JWT_SECRET", None)  # force fallback path

import importlib
import api.middleware.auth as auth
importlib.reload(auth)

import jwt as pyjwt

passed = 0
failed = 0
def assert_(cond, msg):
    global passed, failed
    if cond:
        print("  ok -", msg); passed += 1
    else:
        print("  FAIL -", msg); failed += 1

# 1. Missing secret = graceful fallback, module still loads
print("test 1: env fallback")
assert_(auth.JWT_SECRET.startswith("dev-secret-not-for-production"), "fallback secret used")
assert_(auth.JWT_SECRET, "module loaded without crash")

# 2. alg:none rejected
print("test 2: alg:none rejected")
none_token = pyjwt.encode({"sub": "1", "type": "access"}, key=None, algorithm="none")
try:
    auth.decode_token(none_token)
    assert_(False, "none token should be rejected")
except Exception:
    assert_(True, "alg:none token rejected")

# 3. Valid HS256 access token works
print("test 3: valid token works")
tok = auth.create_access_token({"sub": "user1", "address": "0xabc", "roles": ["admin"]})
payload = auth.decode_token(tok)
assert_(payload["sub"] == "user1", "valid token decodes")
assert_(payload["type"] == "access", "type is access")

# 4. Revoked token fails
print("test 4: revoked token fails")
auth.revoke_token(tok)
try:
    auth.decode_token(tok)
    assert_(False, "revoked token should fail")
except Exception:
    assert_(True, "revoked token rejected")

# 5. Refresh works and rotates
print("test 5: refresh works")
login = auth.generate_login_tokens("user1", "0xabc", ["admin"])
rt = login["refresh_token"]
new_pair = auth.refresh_access_token(rt)
assert_(new_pair["token"] and new_pair["refresh_token"], "new tokens issued")
# old refresh now revoked
try:
    auth.decode_token(rt)
    assert_(False, "used refresh should be revoked")
except Exception:
    assert_(True, "used refresh token revoked after rotation")
# refresh token cannot be used as access
new_access = auth.create_access_token({"sub": "user1", "address": "0xabc"})
try:
    auth.refresh_access_token(new_access)
    assert_(False, "access token should not work as refresh")
except Exception:
    assert_(True, "access token rejected by refresh path")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
