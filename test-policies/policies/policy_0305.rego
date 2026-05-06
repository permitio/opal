package access.validation.action.check.policy_0305

# Auto-generated policy 305
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0305",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0305 = false
allowed_0305 {
    data.policies.access.enabled
}
allowed_0305 {
    input.user.role == "admin"
}
allowed_0305 {
    input.user.active
    input.resource.public
}

# Utility function for user info
