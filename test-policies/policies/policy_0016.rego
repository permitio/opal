package governance.validation.resource.deny.policy_0016

# Auto-generated policy 16
# Package: governance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0016",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0016 {
    input.user.role == "admin"
}
approved_0016 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0016 {
    data.policies.governance.enabled
}
denied_0016 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
