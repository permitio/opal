package governance.monitoring.context.validate.policy_0182

# Auto-generated policy 182
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0182",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0182 {
    input.user.active
    input.resource.public
}
allowed_0182 {
    data.policies.governance.enabled
}

# Utility function for user info
