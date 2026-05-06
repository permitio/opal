package risk.authorization.context.check.policy_0580

# Auto-generated policy 580
# Package: risk.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0580",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0580 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0580 = false
allowed_0580 {
    data.policies.risk.enabled
}
denied_0580 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
