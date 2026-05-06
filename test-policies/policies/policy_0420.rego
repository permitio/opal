package risk.authentication.action.allow.policy_0420

# Auto-generated policy 420
# Package: risk.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0420",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0420 = false
denied_0420 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0420 {
    data.policies.risk.enabled
}

# Utility function for user info
