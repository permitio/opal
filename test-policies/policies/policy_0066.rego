package security.authentication.action.deny.policy_0066

# Auto-generated policy 66
# Package: security.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0066",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0066 {
    input.user.active
    input.resource.public
}
denied_0066 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0066 = false
allowed_0066 {
    data.policies.security.enabled
}

# Utility function for user info
