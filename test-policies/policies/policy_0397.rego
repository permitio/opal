package audit.validation.action.deny.core.policy_0397

# Auto-generated policy 397
# Package: audit.validation.action.deny.core

# Metadata
metadata := {
    "policy_id": "0397",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0397 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0397 {
    input.user.active
    input.resource.public
}
allowed_0397 {
    input.user.role == "admin"
}

# Utility function for user info
