package risk.enforcement.resource.allow.utils.policy_0391

# Auto-generated policy 391
# Package: risk.enforcement.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0391",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0391 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0391 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0391 {
    data.policies.risk.enabled
}
allowed_0391 {
    input.user.role == "admin"
}

# Utility function for user info
