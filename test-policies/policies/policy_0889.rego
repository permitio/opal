package security.authentication.user.deny.utils.policy_0889

# Auto-generated policy 889
# Package: security.authentication.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0889",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0889 {
    data.policies.security.enabled
}
allowed_0889 {
    input.user.active
    input.resource.public
}
default allowed_0889 = false

# Utility function for user info
