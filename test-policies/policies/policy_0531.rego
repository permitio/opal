package security.authentication.resource.check.policy_0531

# Auto-generated policy 531
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0531",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0531 {
    input.user.active
    input.resource.public
}
denied_0531 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
