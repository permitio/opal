package governance.enforcement.action.verify.logic.policy_0581

# Auto-generated policy 581
# Package: governance.enforcement.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0581",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0581 {
    data.policies.governance.enabled
}
allowed_0581 {
    input.user.active
    input.resource.public
}
allowed_0581 {
    input.user.role == "admin"
}

# Utility function for user info
