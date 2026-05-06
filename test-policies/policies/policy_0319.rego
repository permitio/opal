package compliance.authorization.user.deny.policy_0319

# Auto-generated policy 319
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0319",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0319 = false
denied_0319 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0319 {
    input.user.active
    input.resource.public
}

# Utility function for user info
