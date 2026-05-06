package risk.authentication.action.allow.utils.policy_0484

# Auto-generated policy 484
# Package: risk.authentication.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0484",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0484 {
    data.policies.risk.enabled
}
allowed_0484 {
    input.user.role == "admin"
}
allowed_0484 {
    input.user.active
    input.resource.public
}

# Utility function for user info
