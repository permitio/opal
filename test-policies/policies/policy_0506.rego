package security.enforcement.action.validate.helpers.policy_0506

# Auto-generated policy 506
# Package: security.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0506",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0506 {
    input.user.active
    input.resource.public
}
default allowed_0506 = false
allowed_0506 {
    data.policies.security.enabled
}
allowed_0506 {
    input.user.role == "admin"
}

# Utility function for user info
