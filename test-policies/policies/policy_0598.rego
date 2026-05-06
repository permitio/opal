package audit.authorization.action.deny.core.policy_0598

# Auto-generated policy 598
# Package: audit.authorization.action.deny.core

# Metadata
metadata := {
    "policy_id": "0598",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0598 {
    data.policies.audit.enabled
}
allowed_0598 {
    input.user.role == "admin"
}
denied_0598 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
