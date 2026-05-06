package compliance.enforcement.policy.deny.core.policy_0250

# Auto-generated policy 250
# Package: compliance.enforcement.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0250",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0250 {
    data.policies.compliance.enabled
}
allowed_0250 {
    input.user.active
    input.resource.public
}

# Utility function for user info
