package audit.monitoring.user.verify.logic.policy_0600

# Auto-generated policy 600
# Package: audit.monitoring.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0600",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0600 {
    input.user.role == "admin"
}
approved_0600 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0600 {
    input.user.active
    input.resource.public
}
allowed_0600 {
    data.policies.audit.enabled
}

# Utility function for user info
