package security.authentication.user.allow.policy_0497

# Auto-generated policy 497
# Package: security.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0497",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0497 = false
denied_0497 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0497 {
    input.user.role == "admin"
}
allowed_0497 {
    input.user.active
    input.resource.public
}

# Utility function for user info
