package governance.monitoring.action.check.logic.policy_0648

# Auto-generated policy 648
# Package: governance.monitoring.action.check.logic

# Metadata
metadata := {
    "policy_id": "0648",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0648 {
    data.policies.governance.enabled
}
default allowed_0648 = false
allowed_0648 {
    input.user.role == "admin"
}

# Utility function for user info
