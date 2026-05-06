package access.enforcement.action.validate.policy_0056

# Auto-generated policy 56
# Package: access.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0056",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0056 {
    data.policies.access.enabled
}
denied_0056 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0056 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0056 {
    input.user.role == "admin"
}

# Utility function for user info
