package audit.authorization.context.verify.policy_0371

# Auto-generated policy 371
# Package: audit.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0371",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0371 {
    input.user.active
    input.resource.public
}
approved_0371 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0371 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
