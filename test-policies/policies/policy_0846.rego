package governance.validation.resource.validate.policy_0846

# Auto-generated policy 846
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0846",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0846 {
    data.policies.governance.enabled
}
allowed_0846 {
    input.user.active
    input.resource.public
}

# Utility function for user info
