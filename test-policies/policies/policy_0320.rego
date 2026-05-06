package audit.authentication.resource.allow.policy_0320

# Auto-generated policy 320
# Package: audit.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0320",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0320 {
    input.user.role == "admin"
}
approved_0320 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0320 = false

# Utility function for user info
