package security.validation.resource.check.policy_0644

# Auto-generated policy 644
# Package: security.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0644",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0644 = false
allowed_0644 {
    input.user.active
    input.resource.public
}
approved_0644 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0644 {
    input.user.role == "admin"
}

# Utility function for user info
