package access.validation.action.check.policy_0542

# Auto-generated policy 542
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0542",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0542 {
    input.user.role == "admin"
}
allowed_0542 {
    input.user.active
    input.resource.public
}

# Utility function for user info
