package audit.enforcement.resource.deny.policy_0562

# Auto-generated policy 562
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0562",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0562 = false
approved_0562 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0562 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
