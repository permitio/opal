package governance.authentication.action.allow.helpers.policy_0866

# Auto-generated policy 866
# Package: governance.authentication.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0866",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0866 = false
allowed_0866 {
    input.user.active
    input.resource.public
}

# Utility function for user info
