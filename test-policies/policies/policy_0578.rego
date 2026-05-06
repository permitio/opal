package access.authentication.context.check.policy_0578

# Auto-generated policy 578
# Package: access.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0578",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0578 {
    data.policies.access.enabled
}
default allowed_0578 = false
allowed_0578 {
    input.user.active
    input.resource.public
}

# Utility function for user info
