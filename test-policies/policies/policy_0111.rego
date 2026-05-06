package risk.monitoring.resource.check.policy_0111

# Auto-generated policy 111
# Package: risk.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0111",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0111 = false
allowed_0111 {
    input.user.role == "admin"
}
approved_0111 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0111 {
    input.user.active
    input.resource.public
}

# Utility function for user info
