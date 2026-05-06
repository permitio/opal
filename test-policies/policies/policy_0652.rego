package governance.validation.user.deny.policy_0652

# Auto-generated policy 652
# Package: governance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0652",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0652 {
    data.policies.governance.enabled
}
default allowed_0652 = false
denied_0652 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0652 {
    input.user.role == "admin"
}

# Utility function for user info
