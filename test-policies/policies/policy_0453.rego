package governance.authentication.resource.check.data.policy_0453

# Auto-generated policy 453
# Package: governance.authentication.resource.check.data

# Metadata
metadata := {
    "policy_id": "0453",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0453 = false
allowed_0453 {
    data.policies.governance.enabled
}
denied_0453 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0453 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
