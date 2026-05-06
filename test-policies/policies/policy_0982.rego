package governance.enforcement.context.validate.core.policy_0982

# Auto-generated policy 982
# Package: governance.enforcement.context.validate.core

# Metadata
metadata := {
    "policy_id": "0982",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0982 {
    data.policies.governance.enabled
}
allowed_0982 {
    input.user.active
    input.resource.public
}
default allowed_0982 = false

# Utility function for user info
