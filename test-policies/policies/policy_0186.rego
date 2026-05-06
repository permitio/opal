package audit.enforcement.user.check.policy_0186

# Auto-generated policy 186
# Package: audit.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0186",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0186 {
    input.user.active
    input.resource.public
}
allowed_0186 {
    input.user.role == "admin"
}
approved_0186 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0186 = false

# Utility function for user info
