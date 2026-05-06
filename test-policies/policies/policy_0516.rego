package security.validation.context.allow.policy_0516

# Auto-generated policy 516
# Package: security.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0516",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0516 = false
allowed_0516 {
    data.policies.security.enabled
}
allowed_0516 {
    input.user.active
    input.resource.public
}
allowed_0516 {
    input.user.role == "admin"
}

# Utility function for user info
