package compliance.authorization.context.allow.policy_0323

# Auto-generated policy 323
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0323",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0323 {
    input.user.role == "admin"
}
allowed_0323 {
    input.user.active
    input.resource.public
}
approved_0323 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0323 = false

# Utility function for user info
