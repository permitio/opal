package governance.enforcement.action.deny.policy_0827

# Auto-generated policy 827
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0827",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0827 {
    data.policies.governance.enabled
}
allowed_0827 {
    input.user.role == "admin"
}
approved_0827 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
