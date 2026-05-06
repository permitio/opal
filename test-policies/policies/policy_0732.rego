package audit.monitoring.user.allow.policy_0732

# Auto-generated policy 732
# Package: audit.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0732",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0732 {
    input.user.role == "admin"
}
approved_0732 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0732 {
    input.user.active
    input.resource.public
}

# Utility function for user info
