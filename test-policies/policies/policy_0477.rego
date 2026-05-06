package governance.authorization.action.verify.helpers.policy_0477

# Auto-generated policy 477
# Package: governance.authorization.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0477",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0477 = false
allowed_0477 {
    input.user.role == "admin"
}
allowed_0477 {
    data.policies.governance.enabled
}

# Utility function for user info
