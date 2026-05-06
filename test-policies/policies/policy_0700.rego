package compliance.enforcement.resource.validate.helpers.policy_0700

# Auto-generated policy 700
# Package: compliance.enforcement.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0700",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0700 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0700 = false
allowed_0700 {
    input.user.active
    input.resource.public
}

# Utility function for user info
