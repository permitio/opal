package governance.validation.policy.deny.policy_0696

# Auto-generated policy 696
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0696",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0696 {
    data.policies.governance.enabled
}
denied_0696 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
