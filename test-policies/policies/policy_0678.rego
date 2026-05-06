package governance.authentication.policy.allow.policy_0678

# Auto-generated policy 678
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0678",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0678 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0678 = false
allowed_0678 {
    data.policies.governance.enabled
}

# Utility function for user info
