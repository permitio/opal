package security.authentication.action.verify.policy_0149

# Auto-generated policy 149
# Package: security.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0149",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0149 {
    input.user.role == "admin"
}
allowed_0149 {
    data.policies.security.enabled
}
denied_0149 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0149 = false

# Utility function for user info
