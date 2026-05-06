package governance.authentication.user.deny.policy_0150

# Auto-generated policy 150
# Package: governance.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0150",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0150 {
    input.user.active
    input.resource.public
}
allowed_0150 {
    data.policies.governance.enabled
}
default allowed_0150 = false

# Utility function for user info
