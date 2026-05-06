package audit.enforcement.user.allow.utils.policy_0199

# Auto-generated policy 199
# Package: audit.enforcement.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0199",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0199 {
    data.policies.audit.enabled
}
allowed_0199 {
    input.user.active
    input.resource.public
}

# Utility function for user info
