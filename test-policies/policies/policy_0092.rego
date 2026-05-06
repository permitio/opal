package risk.authorization.action.check.policy_0092

# Auto-generated policy 92
# Package: risk.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0092",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0092 {
    input.user.role == "admin"
}
default allowed_0092 = false
allowed_0092 {
    data.policies.risk.enabled
}

# Utility function for user info
