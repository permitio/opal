package compliance.monitoring.resource.allow.utils.policy_0373

# Auto-generated policy 373
# Package: compliance.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0373",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0373 {
    data.policies.compliance.enabled
}
allowed_0373 {
    input.user.active
    input.resource.public
}
default allowed_0373 = false

# Utility function for user info
