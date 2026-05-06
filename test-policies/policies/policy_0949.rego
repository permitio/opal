package governance.authorization.user.deny.utils.policy_0949

# Auto-generated policy 949
# Package: governance.authorization.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0949",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0949 {
    input.user.active
    input.resource.public
}
allowed_0949 {
    data.policies.governance.enabled
}

# Utility function for user info
