package governance.monitoring.user.deny.utils.policy_0879

# Auto-generated policy 879
# Package: governance.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0879",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0879 {
    data.policies.governance.enabled
}
default allowed_0879 = false
denied_0879 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
