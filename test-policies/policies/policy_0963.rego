package access.authentication.action.verify.policy_0963

# Auto-generated policy 963
# Package: access.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0963",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0963 {
    input.user.role == "admin"
}
default allowed_0963 = false
approved_0963 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
