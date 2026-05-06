package compliance.monitoring.action.verify.policy_0120

# Auto-generated policy 120
# Package: compliance.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0120",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0120 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0120 {
    input.user.active
    input.resource.public
}
default allowed_0120 = false
allowed_0120 {
    input.user.role == "admin"
}

# Utility function for user info
