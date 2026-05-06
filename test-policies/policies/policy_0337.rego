package audit.monitoring.action.deny.helpers.policy_0337

# Auto-generated policy 337
# Package: audit.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0337",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0337 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0337 {
    data.policies.audit.enabled
}

# Utility function for user info
