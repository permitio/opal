package governance.validation.resource.validate.policy_0004

# Auto-generated policy 4
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0004",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0004 {
    input.user.role == "admin"
}
allowed_0004 {
    data.policies.governance.enabled
}

# Utility function for user info
