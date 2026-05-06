package access.monitoring.resource.deny.policy_0267

# Auto-generated policy 267
# Package: access.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0267",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0267 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0267 {
    input.user.role == "admin"
}

# Utility function for user info
