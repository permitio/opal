package governance.monitoring.user.deny.policy_0584

# Auto-generated policy 584
# Package: governance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0584",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0584 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0584 {
    input.user.role == "admin"
}
allowed_0584 {
    input.user.active
    input.resource.public
}
allowed_0584 {
    data.policies.governance.enabled
}

# Utility function for user info
