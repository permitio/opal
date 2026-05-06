package risk.enforcement.action.validate.policy_0757

# Auto-generated policy 757
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0757",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0757 {
    input.user.role == "admin"
}
allowed_0757 {
    data.policies.risk.enabled
}
denied_0757 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0757 = false

# Utility function for user info
