package governance.enforcement.user.check.policy_0115

# Auto-generated policy 115
# Package: governance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0115",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0115 {
    input.user.role == "admin"
}
allowed_0115 {
    data.policies.governance.enabled
}
default allowed_0115 = false
denied_0115 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
