package governance.authentication.action.check.logic.policy_0867

# Auto-generated policy 867
# Package: governance.authentication.action.check.logic

# Metadata
metadata := {
    "policy_id": "0867",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0867 {
    data.policies.governance.enabled
}
allowed_0867 {
    input.user.active
    input.resource.public
}
default allowed_0867 = false
allowed_0867 {
    input.user.role == "admin"
}

# Utility function for user info
