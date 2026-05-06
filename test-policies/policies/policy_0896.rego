package compliance.authentication.policy.deny.policy_0896

# Auto-generated policy 896
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0896",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0896 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0896 = false
allowed_0896 {
    data.policies.compliance.enabled
}
allowed_0896 {
    input.user.role == "admin"
}

# Utility function for user info
