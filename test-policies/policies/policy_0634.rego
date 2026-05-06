package governance.enforcement.policy.check.core.policy_0634

# Auto-generated policy 634
# Package: governance.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0634",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0634 {
    input.user.role == "admin"
}
allowed_0634 {
    data.policies.governance.enabled
}
allowed_0634 {
    input.user.active
    input.resource.public
}
denied_0634 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
