package risk.validation.action.check.policy_0726

# Auto-generated policy 726
# Package: risk.validation.action.check

# Metadata
metadata := {
    "policy_id": "0726",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0726 = false
allowed_0726 {
    data.policies.risk.enabled
}
allowed_0726 {
    input.user.active
    input.resource.public
}
denied_0726 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
