package compliance.monitoring.action.allow.policy_0464

# Auto-generated policy 464
# Package: compliance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0464",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0464 {
    input.user.active
    input.resource.public
}
default allowed_0464 = false
approved_0464 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
