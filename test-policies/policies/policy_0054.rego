package governance.authentication.action.deny.policy_0054

# Auto-generated policy 54
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0054",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0054 {
    input.user.role == "admin"
}
default allowed_0054 = false
allowed_0054 {
    data.policies.governance.enabled
}
allowed_0054 {
    input.user.active
    input.resource.public
}

# Utility function for user info
