package security.monitoring.action.verify.policy_0450

# Auto-generated policy 450
# Package: security.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0450",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0450 {
    input.user.active
    input.resource.public
}
approved_0450 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0450 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
