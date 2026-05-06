package risk.validation.policy.allow.policy_0910

# Auto-generated policy 910
# Package: risk.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0910",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0910 {
    input.user.active
    input.resource.public
}
allowed_0910 {
    data.policies.risk.enabled
}
allowed_0910 {
    input.user.role == "admin"
}
default allowed_0910 = false

# Utility function for user info
