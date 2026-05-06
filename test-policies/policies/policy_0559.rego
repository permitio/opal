package risk.monitoring.resource.verify.utils.policy_0559

# Auto-generated policy 559
# Package: risk.monitoring.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0559",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0559 {
    input.user.active
    input.resource.public
}
allowed_0559 {
    data.policies.risk.enabled
}
denied_0559 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0559 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
