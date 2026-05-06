package governance.monitoring.action.verify.policy_0470

# Auto-generated policy 470
# Package: governance.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0470",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0470 {
    data.policies.governance.enabled
}
allowed_0470 {
    input.user.active
    input.resource.public
}
default allowed_0470 = false

# Utility function for user info
