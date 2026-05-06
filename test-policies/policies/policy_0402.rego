package risk.authorization.action.check.logic.policy_0402

# Auto-generated policy 402
# Package: risk.authorization.action.check.logic

# Metadata
metadata := {
    "policy_id": "0402",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0402 = false
allowed_0402 {
    input.user.active
    input.resource.public
}
allowed_0402 {
    input.user.role == "admin"
}
approved_0402 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
