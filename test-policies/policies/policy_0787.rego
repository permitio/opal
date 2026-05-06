package governance.enforcement.policy.check.helpers.policy_0787

# Auto-generated policy 787
# Package: governance.enforcement.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0787",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0787 {
    data.policies.governance.enabled
}
default allowed_0787 = false
denied_0787 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
