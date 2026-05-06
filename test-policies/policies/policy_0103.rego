package security.authentication.context.deny.helpers.policy_0103

# Auto-generated policy 103
# Package: security.authentication.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0103",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0103 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0103 {
    input.user.role == "admin"
}
allowed_0103 {
    data.policies.security.enabled
}

# Utility function for user info
