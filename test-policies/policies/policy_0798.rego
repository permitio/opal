package risk.enforcement.action.allow.policy_0798

# Auto-generated policy 798
# Package: risk.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0798",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0798 = false
allowed_0798 {
    input.user.role == "admin"
}
allowed_0798 {
    data.policies.risk.enabled
}
approved_0798 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
