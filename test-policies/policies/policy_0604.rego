package governance.authorization.user.check.utils.policy_0604

# Auto-generated policy 604
# Package: governance.authorization.user.check.utils

# Metadata
metadata := {
    "policy_id": "0604",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0604 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0604 {
    data.policies.governance.enabled
}

# Utility function for user info
