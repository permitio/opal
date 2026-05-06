package governance.authentication.policy.validate.utils.policy_0536

# Auto-generated policy 536
# Package: governance.authentication.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0536",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0536 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0536 {
    data.policies.governance.enabled
}
default allowed_0536 = false
approved_0536 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
