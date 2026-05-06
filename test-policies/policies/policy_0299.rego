package security.authorization.context.deny.utils.policy_0299

# Auto-generated policy 299
# Package: security.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0299",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0299 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0299 {
    input.user.active
    input.resource.public
}

# Utility function for user info
