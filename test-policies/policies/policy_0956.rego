package governance.authorization.action.validate.helpers.policy_0956

# Auto-generated policy 956
# Package: governance.authorization.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0956",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0956 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0956 {
    data.policies.governance.enabled
}

# Utility function for user info
