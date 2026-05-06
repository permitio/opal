package governance.monitoring.context.deny.policy_0764

# Auto-generated policy 764
# Package: governance.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0764",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0764 {
    data.policies.governance.enabled
}
approved_0764 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
