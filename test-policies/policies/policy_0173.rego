package security.monitoring.user.check.policy_0173

# Auto-generated policy 173
# Package: security.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0173",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0173 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0173 {
    input.user.active
    input.resource.public
}
allowed_0173 {
    input.user.role == "admin"
}

# Utility function for user info
