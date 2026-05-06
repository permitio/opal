package governance.authentication.action.deny.utils.policy_0082

# Auto-generated policy 82
# Package: governance.authentication.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0082",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0082 = false
allowed_0082 {
    input.user.active
    input.resource.public
}

# Utility function for user info
