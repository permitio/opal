package risk.authorization.policy.check.policy_0508

# Auto-generated policy 508
# Package: risk.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0508",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0508 {
    input.user.role == "admin"
}
allowed_0508 {
    data.policies.risk.enabled
}
denied_0508 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0508 = false

# Utility function for user info
