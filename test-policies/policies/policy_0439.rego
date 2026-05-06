package security.authentication.resource.check.policy_0439

# Auto-generated policy 439
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0439",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0439 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0439 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0439 {
    input.user.active
    input.resource.public
}

# Utility function for user info
