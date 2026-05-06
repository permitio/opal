package access.authentication.policy.deny.helpers.policy_0650

# Auto-generated policy 650
# Package: access.authentication.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0650",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0650 {
    input.user.active
    input.resource.public
}
allowed_0650 {
    data.policies.access.enabled
}

# Utility function for user info
