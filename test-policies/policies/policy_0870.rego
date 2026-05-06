package risk.authentication.action.deny.policy_0870

# Auto-generated policy 870
# Package: risk.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0870",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0870 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0870 = false
allowed_0870 {
    input.user.active
    input.resource.public
}

# Utility function for user info
