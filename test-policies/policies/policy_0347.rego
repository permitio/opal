package audit.authorization.user.check.policy_0347

# Auto-generated policy 347
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0347",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0347 = false
allowed_0347 {
    data.policies.audit.enabled
}
allowed_0347 {
    input.user.active
    input.resource.public
}

# Utility function for user info
