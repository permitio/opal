package risk.authorization.action.allow.policy_0943

# Auto-generated policy 943
# Package: risk.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0943",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0943 {
    input.user.active
    input.resource.public
}
allowed_0943 {
    input.user.role == "admin"
}
approved_0943 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
