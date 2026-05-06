package access.authorization.user.deny.policy_0941

# Auto-generated policy 941
# Package: access.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0941",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0941 {
    data.policies.access.enabled
}
denied_0941 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
