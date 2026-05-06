package governance.enforcement.context.check.logic.policy_0741

# Auto-generated policy 741
# Package: governance.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0741",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0741 = false
allowed_0741 {
    data.policies.governance.enabled
}
allowed_0741 {
    input.user.active
    input.resource.public
}

# Utility function for user info
