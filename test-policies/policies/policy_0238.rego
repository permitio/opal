package security.authentication.context.check.policy_0238

# Auto-generated policy 238
# Package: security.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0238",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0238 {
    input.user.role == "admin"
}
denied_0238 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0238 {
    data.policies.security.enabled
}
allowed_0238 {
    input.user.active
    input.resource.public
}

# Utility function for user info
