package audit.enforcement.context.check.policy_0137

# Auto-generated policy 137
# Package: audit.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0137",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0137 = false
allowed_0137 {
    input.user.role == "admin"
}
allowed_0137 {
    input.user.active
    input.resource.public
}
approved_0137 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
