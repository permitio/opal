package governance.validation.action.check.helpers.policy_0865

# Auto-generated policy 865
# Package: governance.validation.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0865",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0865 {
    input.user.active
    input.resource.public
}
default allowed_0865 = false
allowed_0865 {
    data.policies.governance.enabled
}

# Utility function for user info
