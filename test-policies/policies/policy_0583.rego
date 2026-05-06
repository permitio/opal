package audit.enforcement.resource.deny.core.policy_0583

# Auto-generated policy 583
# Package: audit.enforcement.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0583",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0583 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0583 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0583 = false
allowed_0583 {
    data.policies.audit.enabled
}

# Utility function for user info
