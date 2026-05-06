package risk.enforcement.context.allow.core.policy_0174

# Auto-generated policy 174
# Package: risk.enforcement.context.allow.core

# Metadata
metadata := {
    "policy_id": "0174",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0174 {
    data.policies.risk.enabled
}
allowed_0174 {
    input.user.active
    input.resource.public
}
allowed_0174 {
    input.user.role == "admin"
}
approved_0174 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
