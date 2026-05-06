package governance.authorization.policy.validate.policy_0738

# Auto-generated policy 738
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0738",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0738 {
    data.policies.governance.enabled
}
allowed_0738 {
    input.user.active
    input.resource.public
}

# Utility function for user info
