package governance.monitoring.action.verify.utils.policy_0364

# Auto-generated policy 364
# Package: governance.monitoring.action.verify.utils

# Metadata
metadata := {
    "policy_id": "0364",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0364 {
    input.user.active
    input.resource.public
}
approved_0364 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
