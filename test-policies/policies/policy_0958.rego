package governance.authentication.user.verify.policy_0958

# Auto-generated policy 958
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0958",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0958 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0958 {
    data.policies.governance.enabled
}

# Utility function for user info
