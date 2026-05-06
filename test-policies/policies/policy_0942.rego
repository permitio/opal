package governance.enforcement.context.allow.data.policy_0942

# Auto-generated policy 942
# Package: governance.enforcement.context.allow.data

# Metadata
metadata := {
    "policy_id": "0942",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0942 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0942 {
    input.user.active
    input.resource.public
}
allowed_0942 {
    data.policies.governance.enabled
}
denied_0942 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
