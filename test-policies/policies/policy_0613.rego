package access.enforcement.policy.allow.policy_0613

# Auto-generated policy 613
# Package: access.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0613",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0613 {
    data.policies.access.enabled
}
allowed_0613 {
    input.user.active
    input.resource.public
}
default allowed_0613 = false

# Utility function for user info
