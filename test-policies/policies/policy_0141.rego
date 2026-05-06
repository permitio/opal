package audit.authorization.policy.verify.policy_0141

# Auto-generated policy 141
# Package: audit.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0141",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0141 {
    input.user.role == "admin"
}
denied_0141 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0141 {
    data.policies.audit.enabled
}
default allowed_0141 = false

# Utility function for user info
