package audit.validation.action.verify.policy_0605

# Auto-generated policy 605
# Package: audit.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0605",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0605 {
    input.user.active
    input.resource.public
}
approved_0605 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0605 = false

# Utility function for user info
