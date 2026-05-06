package security.authentication.resource.check.logic.policy_0126

# Auto-generated policy 126
# Package: security.authentication.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0126",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0126 = false
allowed_0126 {
    input.user.active
    input.resource.public
}
approved_0126 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
