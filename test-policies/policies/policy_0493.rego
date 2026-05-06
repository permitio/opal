package audit.enforcement.context.deny.core.policy_0493

# Auto-generated policy 493
# Package: audit.enforcement.context.deny.core

# Metadata
metadata := {
    "policy_id": "0493",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0493 {
    input.user.active
    input.resource.public
}
default allowed_0493 = false
allowed_0493 {
    data.policies.audit.enabled
}

# Utility function for user info
